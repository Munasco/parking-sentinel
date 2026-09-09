const assert = require('node:assert/strict');
const { compareFrames } = require('../parking_sentinel/motion.js');
const width = 96, height = 54;
const still = new Uint8ClampedArray(width * height * 4);
assert.equal(compareFrames(null, still, width, height).detected, false);
assert.equal(compareFrames(still, still, width, height).detected, false);
const moving = new Uint8ClampedArray(still);
for (let y = 10; y < 20; y++) {
  for (let x = 30; x < 40; x++) {
    const offset = (y * width + x) * 4;
    moving[offset] = moving[offset + 1] = moving[offset + 2] = 180;
  }
}
const result = compareFrames(still, moving, width, height);
assert.equal(result.detected, true);
assert.equal(result.changed, 100);
assert.deepEqual(result.box, { x: 30 / width, y: 10 / height, width: 10 / width, height: 10 / height });
const noise = new Uint8ClampedArray(still).fill(5);
assert.equal(compareFrames(still, noise, width, height).detected, false);
assert.throws(() => compareFrames(still, moving, 2, 2), /Invalid frame dimensions/);
console.log('Motion tests passed: baseline, static scene, moving region, bounding box, noise, dimensions.');
