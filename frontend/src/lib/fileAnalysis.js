const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const DELIMITERS = [",", ";", "\t", "|"];

export async function inspectFile(file) {
  const extension = getExtension(file.name);

  if (extension === ".xlsx") {
    return inspectSpreadsheet(file);
  }

  return inspectTextFile(file);
}

function getExtension(filename) {
  const dotIndex = filename.lastIndexOf(".");
  if (dotIndex === -1) {
    return "";
  }

  return filename.slice(dotIndex).toLowerCase();
}

async function inspectSpreadsheet(file) {
  const XLSX = await import("xlsx");
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: "array" });

  for (const sheetName of workbook.SheetNames) {
    const worksheet = workbook.Sheets[sheetName];
    const rows = XLSX.utils.sheet_to_json(worksheet, {
      header: 1,
      blankrows: false,
      defval: "",
      raw: false,
    });
    const normalizedRows = rows
      .map((row) => row.map((value) => String(value ?? "").trim()))
      .filter((row) => row.some(Boolean));

    const rowCount = countEmailRows(normalizedRows);
    if (rowCount > 0) {
      return {
        fileName: file.name,
        rowCount,
      };
    }
  }

  return {
    fileName: file.name,
    rowCount: 0,
  };
}

async function inspectTextFile(file) {
  const text = await file.text();
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) {
    return {
      fileName: file.name,
      rowCount: 0,
    };
  }

  if (!hasDelimiter(lines)) {
    const rowCount = countEmailRows(lines.map((line) => [line]));
    return {
      fileName: file.name,
      rowCount,
    };
  }

  const delimiter = detectDelimiter(lines.slice(0, 20).join("\n"));
  const rows = lines.map((line) => line.split(delimiter).map((value) => value.trim()));

  return {
    fileName: file.name,
    rowCount: countEmailRows(rows),
  };
}

function countEmailRows(rows) {
  const detection = detectEmailColumn(rows);
  if (!detection) {
    return rows.length;
  }

  const startIndex = detection.hasHeader ? 1 : 0;
  let total = 0;

  for (const row of rows.slice(startIndex)) {
    const candidate = row[detection.columnIndex] || "";
    if (candidate && (EMAIL_PATTERN.test(candidate.toLowerCase()) || candidate.includes("@"))) {
      total += 1;
    }
  }

  return total;
}

function detectEmailColumn(rows) {
  if (!rows.length) {
    return null;
  }

  const headerRow = rows[0];
  for (let index = 0; index < headerRow.length; index += 1) {
    if (String(headerRow[index] || "").toLowerCase().includes("email")) {
      return { columnIndex: index, hasHeader: true };
    }
  }

  let bestColumnIndex = -1;
  let bestScore = 0;
  const columnCount = Math.max(...rows.map((row) => row.length));
  const sample = rows.slice(0, 100);

  for (let columnIndex = 0; columnIndex < columnCount; columnIndex += 1) {
    let score = 0;

    for (const row of sample) {
      const candidate = String(row[columnIndex] || "").trim().toLowerCase();
      if (!candidate) {
        continue;
      }

      if (EMAIL_PATTERN.test(candidate)) {
        score += 3;
      } else if (candidate.includes("@")) {
        score += 1;
      }
    }

    if (score > bestScore) {
      bestScore = score;
      bestColumnIndex = columnIndex;
    }
  }

  if (bestColumnIndex === -1) {
    return null;
  }

  return { columnIndex: bestColumnIndex, hasHeader: false };
}

function hasDelimiter(lines) {
  return lines.some((line) => DELIMITERS.some((delimiter) => line.includes(delimiter)));
}

function detectDelimiter(sample) {
  let winningDelimiter = ",";
  let winningCount = 0;

  for (const delimiter of DELIMITERS) {
    const count = sample.split(delimiter).length;
    if (count > winningCount) {
      winningCount = count;
      winningDelimiter = delimiter;
    }
  }

  return winningDelimiter;
}
