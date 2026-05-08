const activeJobs = new Map();

function startSchedule(userId) {
  stopSchedule(userId);
  const flag = { stopped: false };
  activeJobs.set(userId, flag);
  return flag;
}

function stopSchedule(userId) {
  const existing = activeJobs.get(userId);
  if (existing) {
    existing.stopped = true;
    activeJobs.delete(userId);
    console.log(`[Scheduler] User ${userId} broadcast stopped`);
  }
}

function isActive(userId) {
  return activeJobs.has(userId);
}

module.exports = { startSchedule, stopSchedule, isActive };
