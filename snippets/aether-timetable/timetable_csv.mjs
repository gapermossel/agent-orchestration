/* Timetable CSV export/import that survives a round trip through Excel.
   Excerpt from a desktop timetabling app (React + Electron, runs offline,
   English/Afrikaans). Shown here as a self-contained excerpt.

   - UTF-8 BOM so Excel on Windows reads accented subject names correctly.
   - A `sep=,` hint line, because many regional Windows settings use ';' as
     the list separator and Excel would otherwise put everything in one column.
   - RFC 4180 quoting: commas, quotes and newlines inside a field are safe.
   - Import accepts its own output (BOM and hint line included), so
     export -> edit in Excel -> import gives back the same grid.

   Run: node timetable_csv.mjs   (round-trip self-test) */

function csvField(value) {
  const s = value == null ? '' : String(value);
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

export function exportTimetableCSV(tt, grades, days, periodsPerDay) {
  const rows = [['Grade', 'Day', 'Period', 'Subject', 'Teacher']];
  for (const g of grades) for (const d of days) for (let p = 0; p < periodsPerDay; p++) {
    const c = (tt[g] && tt[g][d] && tt[g][d][p]) || {};
    rows.push([g, d, p + 1, c.subject || '', c.teacher || '']);   // breaks stay in, so the grid shape is kept
  }
  return '\uFEFF' + 'sep=,\r\n' + rows.map(r => r.map(csvField).join(',')).join('\r\n') + '\r\n';
}

/* Split text into records (quoted newlines stay inside a field), then records into fields. */
function parseCSV(text) {
  const records = []; let rec = [], field = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') q = false;
      else field += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') { rec.push(field); field = ''; }
    else if (ch === '\n') { rec.push(field); records.push(rec); rec = []; field = ''; }
    else if (ch !== '\r') field += ch;
  }
  if (field.length || rec.length) { rec.push(field); records.push(rec); }
  return records.filter(r => r.some(f => f.trim() !== ''));
}

export function importTimetableCSV(text) {
  let raw = String(text ?? '');
  if (raw.charCodeAt(0) === 0xFEFF) raw = raw.slice(1);
  let records = parseCSV(raw);
  if (records.length && /^sep\s*=/i.test(records[0][0].trim())) records = records.slice(1);
  if (!records.length) return { headers: [], rows: [] };
  const [headers, ...data] = records;
  return {
    headers,
    rows: data.map(c => ({ grade: c[0] ?? '', day: c[1] ?? '', period: Number(c[2]) || 0, subject: c[3] ?? '', teacher: c[4] ?? '' })),
  };
}

/* Rebuild the nested grid from imported rows; rows for unknown grades/days/periods are ignored. */
export function timetableFromRows(rows, grades, days, periodsPerDay) {
  const tt = {};
  for (const g of grades) { tt[g] = {}; for (const d of days) { tt[g][d] = {}; for (let p = 0; p < periodsPerDay; p++) tt[g][d][p] = null; } }
  for (const r of rows) {
    const p = r.period - 1;
    if (!tt[r.grade] || !tt[r.grade][r.day] || p < 0 || p >= periodsPerDay || !r.subject) continue;
    tt[r.grade][r.day][p] = { subject: r.subject, teacher: r.teacher };
  }
  return tt;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const grades = ['Grade 8'], days = ['Monday', 'Tuesday'], n = 3;
  const tt = { 'Grade 8': {
    Monday: { 0: { subject: 'Mathematics', teacher: 'Teacher A' }, 1: { subject: 'Life Skills, "Health"', teacher: 'Teacher B' }, 2: null },
    Tuesday: { 0: { subject: 'Art\nand Design', teacher: 'Teacher C' }, 1: { subject: '---BLOCKED---', teacher: '' }, 2: { subject: 'Français', teacher: 'Teacher D' } },
  } };
  const csv = exportTimetableCSV(tt, grades, days, n);
  const back = timetableFromRows(importTimetableCSV(csv).rows, grades, days, n);
  const same = JSON.stringify(back) === JSON.stringify(tt);
  console.log(csv.split('\r\n').slice(0, 3).join(' | '));
  console.log(same ? 'round trip OK' : 'round trip MISMATCH');
  process.exitCode = same ? 0 : 1;
}
