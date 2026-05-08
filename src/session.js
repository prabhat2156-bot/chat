const sessions = new Map();

function getSession(userId) {
  if (!sessions.has(userId)) {
    sessions.set(userId, {
      state: "idle",
      delaySeconds: 3,
      repeatHours: 1,
      scheduleDays: null,
      broadcastActive: false,
      broadcastEndTime: null,
      broadcastCycles: 0,
      wa1Groups: [],
      wa2Groups: [],
      selectedWa1Ids: [],
      selectedWa2Ids: [],
      selectionMsgId: undefined,
    });
  }
  return sessions.get(userId);
}

function updateSession(userId, patch) {
  const session = getSession(userId);
  sessions.set(userId, { ...session, ...patch });
}

module.exports = { getSession, updateSession };
