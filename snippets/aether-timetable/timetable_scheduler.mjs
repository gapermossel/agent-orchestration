/* Weekly timetable generator: greedy block placement, then simulated annealing.
   Excerpt from a desktop timetabling app (React + Electron, runs offline,
   English/Afrikaans). Trimmed (no locked lessons, priorities or UI labels)
   and shown here as a self-contained excerpt.

   Hard constraints (never broken): blocked slots such as breaks, one lesson
   per grade per slot, a teacher in one place at a time, and teacher
   unavailability.
   Soft goals (scored): the weekly period count per subject, consecutive
   "succession blocks" (e.g. 4 periods as [2,2] or [3,1]), no scattered
   same-day repeats, and bigger blocks earlier in the week.
   The RNG is seeded, so the same seed always gives the same timetable. */
const BLOCKED = '---BLOCKED---';

export class Scheduler {
  constructor(cfg) {
    Object.assign(this, { days: cfg.days, grades: cfg.grades, periodsPerDay: cfg.periodsPerDay });
    this.blockedSlots = cfg.blockedSlots || {};          // { day: { period: 'BREAK' } }
    this.teacherUnavailable = cfg.teacherUnavailable || {}; // { teacher: { day: { period: true } } }
    this.requirements = cfg.requirements || [];          // [{ grade, subject, teacher, periodsPerWeek }]
    this.successionRules = cfg.successionRules || {};    // { subject: { values: [2, 2] } }
    this.rng = makeRng(cfg.seed || 1);
  }

  /* Block sizes (1..3) that sum exactly to periods/week; a short rule list is padded with singles. */
  successionBlocks(subject, needed) {
    const raw = (this.successionRules[subject] || {}).values || [];
    const blocks = []; let sum = 0;
    for (const v of raw) {
      const size = Math.min(3, Math.max(1, Math.round(Number(v) || 1)));
      if (sum + size > needed) break;
      blocks.push(size); sum += size;
    }
    while (sum < needed) { blocks.push(1); sum += 1; }
    return blocks;
  }

  cell(tt, g, d, p) { return tt[g] && tt[g][d] && tt[g][d][p]; }
  isBlocked(d, p) { return !!(this.blockedSlots[d] && this.blockedSlots[d][p]); }
  unavailable(t, d, p) { return !!(t && this.teacherUnavailable[t] && this.teacherUnavailable[t][d] && this.teacherUnavailable[t][d][p]); }
  teacherBusy(tt, t, d, p, exceptGrade) {
    return !!t && this.grades.some(g => g !== exceptGrade && (this.cell(tt, g, d, p) || {}).teacher === t);
  }
  countOnDay(tt, g, d, subject) {
    let n = 0; for (let p = 0; p < this.periodsPerDay; p++) if ((this.cell(tt, g, d, p) || {}).subject === subject) n++;
    return n;
  }

  canPlaceBlock(tt, g, d, start, size, subject, teacher) {
    if (start + size > this.periodsPerDay || this.countOnDay(tt, g, d, subject) > 0) return false;
    for (let p = start; p < start + size; p++) {
      if (this.isBlocked(d, p) || tt[g][d][p] || this.unavailable(teacher, d, p) || this.teacherBusy(tt, teacher, d, p, g)) return false;
    }
    return true;
  }

  // Prefer early days/periods, more strongly for larger blocks.
  slotScore(size, d, p) {
    const dw = this.days.indexOf(d) / Math.max(this.days.length - 1, 1), pw = p / Math.max(this.periodsPerDay - 1, 1);
    return size * 10 - (dw + pw) * size;
  }

  generate() {
    const tt = {};
    for (const g of this.grades) {
      tt[g] = {};
      for (const d of this.days) {
        tt[g][d] = {};
        for (let p = 0; p < this.periodsPerDay; p++) tt[g][d][p] = this.isBlocked(d, p) ? { subject: BLOCKED, teacher: '' } : null;
      }
    }
    // Most-demanding subjects first: they have the fewest legal placements.
    const reqs = [...this.requirements].sort((a, b) => b.periodsPerWeek - a.periodsPerWeek);
    for (const r of reqs) {
      for (const size of this.successionBlocks(r.subject, r.periodsPerWeek)) {
        const options = [];
        for (const d of this.days) for (let p = 0; p + size <= this.periodsPerDay; p++) {
          if (this.canPlaceBlock(tt, r.grade, d, p, size, r.subject, r.teacher)) options.push({ d, p, s: this.slotScore(size, d, p) + this.rng() * 2 });
        }
        options.sort((a, b) => b.s - a.s);
        const best = options[0];
        if (!best) continue;                 // left unplaced; the conflict report will show it
        for (let i = 0; i < size; i++) tt[r.grade][best.d][best.p + i] = { subject: r.subject, teacher: r.teacher || '', blockSize: size };
      }
    }
    return tt;
  }

  score(tt) {
    let score = 0;
    for (const r of this.requirements) {
      const blocks = this.successionBlocks(r.subject, r.periodsPerWeek), maxBlock = Math.max(1, ...blocks);
      let placed = 0;
      for (const d of this.days) {
        const pos = [];
        for (let p = 0; p < this.periodsPerDay; p++) if ((this.cell(tt, r.grade, d, p) || {}).subject === r.subject) pos.push(p);
        placed += pos.length;
        const consecutive = pos.every((p, i) => i === 0 || p - pos[i - 1] === 1);
        if (pos.length > maxBlock) score -= 20;
        if (pos.length >= 2 && !consecutive) score -= 30;
        if (pos.length && consecutive && blocks.includes(pos.length)) score += 10;
      }
      score -= Math.abs(placed - r.periodsPerWeek) * 10;
    }
    return score;
  }

  /* Simulated annealing: random same-day and cross-day swaps within a grade.
     Hard constraints are checked before a swap is scored, so the result is always legal. */
  optimise(tt, iterations = 2000) {
    let cur = structuredClone(tt), curScore = this.score(cur), best = cur, bestScore = curScore;
    const T0 = 50, Tmin = 0.1, pick = arr => arr[Math.floor(this.rng() * arr.length)];
    for (let i = 0; i < iterations; i++) {
      const T = T0 * Math.pow(Tmin / T0, i / iterations);
      const g = pick(this.grades), d1 = pick(this.days), d2 = pick(this.days);
      const p1 = Math.floor(this.rng() * this.periodsPerDay), p2 = Math.floor(this.rng() * this.periodsPerDay);
      if (d1 === d2 && p1 === p2) continue;
      const c1 = cur[g][d1][p1], c2 = cur[g][d2][p2];
      if ((c1 && c1.subject === BLOCKED) || (c2 && c2.subject === BLOCKED)) continue;
      const cand = structuredClone(cur);
      cand[g][d1][p1] = c2; cand[g][d2][p2] = c1;
      if (c1 && (this.unavailable(c1.teacher, d2, p2) || this.teacherBusy(cand, c1.teacher, d2, p2, g))) continue;
      if (c2 && (this.unavailable(c2.teacher, d1, p1) || this.teacherBusy(cand, c2.teacher, d1, p1, g))) continue;
      const s = this.score(cand), delta = s - curScore;
      if (delta > 0 || Math.exp(delta / T) > this.rng()) {      // sometimes accept worse, to escape local optima
        cur = cand; curScore = s;
        if (s > bestScore) { best = cand; bestScore = s; }
      }
    }
    return best;
  }
}

// Small linear congruential generator: deterministic for a given seed.
export function makeRng(seed) {
  let s = seed >>> 0;
  return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 0x100000000; };
}

export { BLOCKED };
