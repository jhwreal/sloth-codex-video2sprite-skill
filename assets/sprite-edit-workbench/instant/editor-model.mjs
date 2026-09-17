// Asset-independent playback and version rules. Frame indices are zero-based internally.
export function versionsFor(entry, known = []) {
  const legacy = [['h3Candidate', 'H3 v1'], ['compactCandidate', '轻量抽帧 v1'],
    ['idleCandidate', '待机剪辑'], ['walkCandidate', '移动剪辑']];
  const configured = entry.candidates || [];
  const candidates = configured.concat(legacy.flatMap(([key, label]) =>
    entry[key] && !configured.some(v => v.manifest === entry[key].manifest) ? [{...entry[key], label}] : []));
  const byKey = new Map(known.map(v => [v.key, v]));
  for (const v of candidates) {
    const key = v.manifest || v.id;
    if (key) byKey.set(key, {...v, key, label: v.label || v.name || v.id});
  }
  return [...byKey.values()];
}
export function chooseVersion(versions, remembered) {
  return remembered === 'reference' || versions.some(v => v.key === remembered)
    ? remembered : versions.at(-1)?.key || 'reference';
}
export function timelineFor(frames, draft) {
  const excluded = new Set(draft.excluded || []);
  const fps = Math.max(1, Number(draft.fps) || 24);
  const speed = Math.max(.1, Number(draft.speed) || 1);
  let time = 0;
  return frames.flatMap((frame, index) => {
    if (excluded.has(index) || index < draft.start - 1 || index > draft.end - 1) return [];
    const ticks = draft.timing === 'uniform' ? 1 : (Number.isFinite(frame.duration_ticks) && frame.duration_ticks > 0 ? frame.duration_ticks : 1);
    const duration = ticks / fps / speed;
    const item = {index, start: time, duration}; time += duration;
    return [item];
  });
}
export function frameAt(timeline, seconds) {
  return timeline.findIndex(item => seconds < item.start + item.duration);
}
