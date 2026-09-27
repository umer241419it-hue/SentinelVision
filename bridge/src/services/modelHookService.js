'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const HOOKS_FILE = path.resolve(__dirname, '../../../data/model_hooks.json');
let hooks = [];

function load() {
    try {
        hooks = fs.existsSync(HOOKS_FILE) ? JSON.parse(fs.readFileSync(HOOKS_FILE, 'utf8')) : [];
    } catch {
        hooks = [];
    }
}

function save() {
    fs.mkdirSync(path.dirname(HOOKS_FILE), { recursive: true });
    fs.writeFileSync(HOOKS_FILE, JSON.stringify(hooks, null, 2), 'utf8');
}

function listHooks() {
    return hooks;
}

function upsertHook({ modelId, modelName, contributorId, contributorName, driftMonitoring, inferenceProvenance }) {
    if (!modelId) throw new Error('Model is required');
    if (!driftMonitoring && !inferenceProvenance) {
        throw new Error('Select at least one hook: Drift Monitoring or Inference Provenance');
    }

    const now = new Date().toISOString();
    const existing = hooks.find(h => h.modelId === modelId);
    const hook = existing || {
        hookId: `hook-${crypto.randomBytes(6).toString('hex')}`,
        createdAt: now
    };

    Object.assign(hook, {
        modelId,
        modelName: modelName || modelId,
        contributorId: contributorId || 'unassigned',
        contributorName: contributorName || 'Unassigned',
        driftMonitoring: Boolean(driftMonitoring),
        inferenceProvenance: Boolean(inferenceProvenance),
        status: 'ACTIVE',
        updatedAt: now,
        integration: {
            drift: driftMonitoring ? 'REGISTERED' : 'DISABLED',
            provenance: inferenceProvenance ? 'REGISTERED' : 'DISABLED'
        }
    });

    if (!existing) hooks.unshift(hook);
    save();
    return hook;
}

function disableHook(hookId) {
    const hook = hooks.find(h => h.hookId === hookId);
    if (!hook) return null;
    hook.status = 'DISABLED';
    hook.updatedAt = new Date().toISOString();
    save();
    return hook;
}

load();

module.exports = { listHooks, upsertHook, disableHook };
