// SPDX-License-Identifier: MPL-2.0
// One scan per visit; a detection flicker cannot count as a new visitor.
class PresenceGate {
  constructor() { this.armed = true; this.clearCandidate(); this.absentSince = null; }
  clearCandidate() { this.seenSince = null; this.hits = 0; }
  consume() { this.armed = false; this.clearCandidate(); this.absentSince = null; }
  update(present, now) {
    if (present) {
      this.absentSince = null;
      if (!this.armed) return 'served';
      this.seenSince ??= now; this.hits++;
      return now - this.seenSince >= 2500 && this.hits >= 3 ? 'ready' : 'holding';
    }
    this.clearCandidate();
    if (!this.armed) {
      this.absentSince ??= now;
      if (now - this.absentSince < 4000) return 'served';
      this.armed = true; this.absentSince = null;
      return 'rearmed';
    }
    return 'waiting';
  }
}
