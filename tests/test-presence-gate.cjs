const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const Gate = vm.runInNewContext(fs.readFileSync('smart-mirror-laptop/assets/presence-gate.js','utf8') + '\nPresenceGate');
const gate = new Gate();
assert.equal(gate.update(false,0),'waiting');
assert.equal(gate.update(true,1000),'holding');
assert.equal(gate.update(false,2000),'waiting'); // a passing glimpse cannot trigger
assert.equal(gate.update(true,3000),'holding');
assert.equal(gate.update(true,4300),'holding');
assert.equal(gate.update(true,5600),'ready');
gate.consume();
assert.equal(gate.update(true,9000),'served'); // no repeat while standing there
assert.equal(gate.update(false,10000),'served');
assert.equal(gate.update(true,12000),'served'); // a brief detection loss cannot rearm
assert.equal(gate.update(false,13000),'served');
assert.equal(gate.update(false,16999),'served');
assert.equal(gate.update(false,17000),'rearmed');
assert.equal(gate.update(true,18000),'holding');
assert.equal(gate.update(true,19400),'holding');
assert.equal(gate.update(true,20600),'ready'); // next visitor triggers again
console.log('PASS: arrival stability, one scan per visit, flicker rejection, departure and re-entry');
