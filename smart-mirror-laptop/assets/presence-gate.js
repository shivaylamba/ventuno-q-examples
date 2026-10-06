// SPDX-License-Identifier: MPL-2.0
// Require a stable detection before each automatic scan. The same person may
// trigger another scan after the result screen resets.
class PresenceGate {
  constructor() { this.armed = true; this.clearCandidate(); }
  clearCandidate() { this.seenSince = null; this.hits = 0; }
  consume() { this.armed = false; this.clearCandidate(); }
  rearm() { this.armed = true; this.clearCandidate(); }
  update(present, now) {
    if (present) {
      if (!this.armed) return 'blocked';
      this.seenSince ??= now; this.hits++;
      return now - this.seenSince >= 2500 && this.hits >= 3 ? 'ready' : 'holding';
    }
    this.clearCandidate();
    return 'waiting';
  }
}
