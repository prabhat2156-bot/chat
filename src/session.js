/**
 * In-memory session for UI state (delay, mode, etc.)
 * Not persisted — resets on restart.
 * Broadcast state is persisted separately in MongoDB.
 */
const sessions = new Map();

const MAX_ACCOUNTS = 10;

function defaultSession() {
  return {
    state: "idle",
    delaySeconds: 5,
    repeatHours: 1,
    scheduleDays: null,
    conversationMode: true,
    // Broadcast setup state
    selectedAccountIndices: [],
    connectingAccountIndex: null,
    selectionMsgId: undefined,
    // Account setup
    awaitingPhoneForIndex: null,
  };
}

function getSession(userId) {
  if (!sessions.has(userId)) sessions.set(userId, defaultSession());
  return sessions.get(userId);
}

function updateSession(userId, patch) {
  const s = getSession(userId);
  sessions.set(userId, { ...s, ...patch });
}

function resetSession(userId) {
  sessions.set(userId, defaultSession());
}

module.exports = { getSession, updateSession, resetSession, MAX_ACCOUNTS };
