/* Conflict report for a generated timetable, plus a runnable demo.
   Excerpt from a desktop timetabling app (React + Electron, runs offline,
   English/Afrikaans). English messages only here. Shown as a
   self-contained excerpt; uses timetable_scheduler.mjs from this folder.

   The generator never knowingly breaks a hard rule, but people can edit the
   grid by hand and import CSVs. So the report re-checks everything from
   scratch, against the timetable only, and returns plain-language items
   tagged error / warning / info.

   Run: node timetable_conflicts.mjs */
import { Scheduler, BLOCKED } from './timetable_scheduler.mjs';

export function analyseConflicts(tt, cfg) {
  const { grades, days, periodsPerDay, requirements = [], teacherUnavailable = {} } = cfg;
  const out = [];
  const cell = (g, d, p) => tt[g] && tt[g][d] && tt[g][d][p];
  const isLesson = c => c && c.subject && c.subject !== BLOCKED;

  // 1. Periods the generator could not place.
  for (const r of requirements) {
    let placed = 0;
    for (const d of days) for (let p = 0; p < periodsPerDay; p++) if ((cell(r.grade, d, p) || {}).subject === r.subject) placed++;
    if (placed < r.periodsPerWeek) out.push({ type: 'error', msg: `${r.grade} – ${r.subject}: only ${placed}/${r.periodsPerWeek} periods placed.` });
  }

  // 2. A teacher in two grades in the same slot.
  for (const d of days) for (let p = 0; p < periodsPerDay; p++) {
    const seen = new Map();
    for (const g of grades) {
      const c = cell(g, d, p);
      if (!isLesson(c) || !c.teacher) continue;
      if (seen.has(c.teacher)) out.push({ type: 'error', msg: `Teacher clash: ${c.teacher} is in ${seen.get(c.teacher)} AND ${g} on ${d} P${p + 1}.` });
      else seen.set(c.teacher, g);
    }
  }

  // 3. A teacher scheduled in a slot marked unavailable.
  for (const g of grades) for (const d of days) for (let p = 0; p < periodsPerDay; p++) {
    const c = cell(g, d, p);
    if (isLesson(c) && c.teacher && ((teacherUnavailable[c.teacher] || {})[d] || {})[p]) {
      out.push({ type: 'error', msg: `${c.teacher} is marked unavailable on ${d} P${p + 1} but is scheduled in ${g}.` });
    }
  }

  // 4. Grade slots left empty (not a break, no lesson).
  for (const g of grades) {
    let empty = 0;
    for (const d of days) for (let p = 0; p < periodsPerDay; p++) if (!cell(g, d, p)) empty++;
    if (empty) out.push({ type: 'info', msg: `${g}: ${empty} slot(s) left empty (no requirement assigned).` });
  }
  return out;
}

/* ---------- demo with made-up data ---------- */
if (import.meta.url === `file://${process.argv[1]}`) {
  const cfg = {
    days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
    grades: ['Grade 8', 'Grade 9'],
    periodsPerDay: 6,
    blockedSlots: Object.fromEntries(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'].map(d => [d, { 3: 'BREAK' }])),
    teacherUnavailable: { 'Teacher B': { Friday: { 0: true, 1: true, 2: true, 4: true, 5: true } } },
    requirements: [
      { grade: 'Grade 8', subject: 'Mathematics', teacher: 'Teacher A', periodsPerWeek: 6 },
      { grade: 'Grade 9', subject: 'Mathematics', teacher: 'Teacher A', periodsPerWeek: 6 },
      { grade: 'Grade 8', subject: 'Science', teacher: 'Teacher B', periodsPerWeek: 4 },
      { grade: 'Grade 9', subject: 'Science', teacher: 'Teacher B', periodsPerWeek: 4 },
      { grade: 'Grade 8', subject: 'English', teacher: 'Teacher C', periodsPerWeek: 5 },
      { grade: 'Grade 9', subject: 'English', teacher: 'Teacher C', periodsPerWeek: 5 },
    ],
    successionRules: { Mathematics: { values: [2, 2, 1, 1] }, Science: { values: [2, 2] } },
    seed: 42,
  };
  const s = new Scheduler(cfg);
  const first = s.generate();
  const best = s.optimise(first, 3000);
  console.log('score greedy', s.score(first), '-> annealed', s.score(best));
  for (const w of analyseConflicts(best, cfg)) console.log(`[${w.type}] ${w.msg}`);
  // Hand-edit that double-books a teacher, to show the report catching it.
  const edited = structuredClone(best);
  edited['Grade 9'].Monday[0] = { ...edited['Grade 8'].Monday[0] };
  const clash = analyseConflicts(edited, cfg).filter(w => w.msg.startsWith('Teacher clash'));
  console.log(clash.length ? `[error] ${clash[0].msg}` : 'no clash (slot was empty)');
}
