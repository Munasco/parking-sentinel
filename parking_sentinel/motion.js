/* Pixel-based trigger used by the real-time video player and Node tests. */
(function (root) {
  function compareFrames(previous, current, width, height) {
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 ||
        current.length !== width * height * 4 || (previous && previous.length !== current.length)) {
      throw new Error('Invalid frame dimensions');
    }
    if (!previous) return { detected: false, score: 0, changed: 0, box: null };
    let total = 0, changed = 0, minX = width, minY = height, maxX = -1, maxY = -1;
    for (let pixel = 0; pixel < width * height; pixel++) {
      const i = pixel * 4;
      const difference = (Math.abs(current[i] - previous[i]) +
        Math.abs(current[i + 1] - previous[i + 1]) +
        Math.abs(current[i + 2] - previous[i + 2])) / 3;
      total += difference;
      if (difference > 28) {
        changed++;
        const x = pixel % width, y = Math.floor(pixel / width);
        minX = Math.min(minX, x); maxX = Math.max(maxX, x);
        minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      }
    }
    const score = total / (width * height);
    const detected = changed >= Math.max(6, Math.ceil(width * height * 0.003)) && score >= 0.4;
    return { detected, score, changed, box: detected ? {
      x: minX / width, y: minY / height,
      width: (maxX - minX + 1) / width, height: (maxY - minY + 1) / height
    } : null };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { compareFrames };
  else root.SentinelMotion = { compareFrames };
})(typeof window !== 'undefined' ? window : this);
