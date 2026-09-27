'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const JWT_SECRET = process.env.JWT_SECRET || 'sentinelvision-secret-jwt-key-2026-production';
const USERS_FILE = path.resolve(__dirname, '../../../data/users.json');

// Ensure data directory exists
const dataDir = path.dirname(USERS_FILE);
if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
}

function hashPassword(password, salt) {
    if (!salt) {
        salt = crypto.randomBytes(16).toString('hex');
    }
    const hash = crypto.pbkdf2Sync(password, salt, 100000, 64, 'sha512').toString('hex');
    return `${salt}:${hash}`;
}

function verifyPassword(password, stored) {
    if (!stored || !stored.includes(':')) return false;
    const [salt, originalHash] = stored.split(':');
    const hash = crypto.pbkdf2Sync(password, salt, 100000, 64, 'sha512').toString('hex');
    return crypto.timingSafeEqual(Buffer.from(hash, 'hex'), Buffer.from(originalHash, 'hex'));
}

function base64UrlEncode(str) {
    return Buffer.from(str)
        .toString('base64')
        .replace(/=/g, '')
        .replace(/\+/g, '-')
        .replace(/\//g, '_');
}

function base64UrlDecode(str) {
    str = str.replace(/-/g, '+').replace(/_/g, '/');
    while (str.length % 4) {
        str += '=';
    }
    return Buffer.from(str, 'base64').toString('utf8');
}

function signJwt(payload, secret = JWT_SECRET, expiresInSeconds = 86400) {
    const header = { alg: 'HS256', typ: 'JWT' };
    const now = Math.floor(Date.now() / 1000);
    const expPayload = {
        ...payload,
        iat: now,
        exp: now + expiresInSeconds
    };

    const headerB64 = base64UrlEncode(JSON.stringify(header));
    const payloadB64 = base64UrlEncode(JSON.stringify(expPayload));
    const data = `${headerB64}.${payloadB64}`;

    const signature = crypto
        .createHmac('sha256', secret)
        .update(data)
        .digest('base64')
        .replace(/=/g, '')
        .replace(/\+/g, '-')
        .replace(/\//g, '_');

    return `${data}.${signature}`;
}

function verifyJwt(token, secret = JWT_SECRET) {
    if (!token || typeof token !== 'string') return null;
    const parts = token.split('.');
    if (parts.length !== 3) return null;

    const [headerB64, payloadB64, signature] = parts;
    const data = `${headerB64}.${payloadB64}`;

    const expectedSig = crypto
        .createHmac('sha256', secret)
        .update(data)
        .digest('base64')
        .replace(/=/g, '')
        .replace(/\+/g, '-')
        .replace(/\//g, '_');

    try {
        if (!crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expectedSig))) {
            return null;
        }
    } catch {
        return null;
    }

    try {
        const payload = JSON.parse(base64UrlDecode(payloadB64));
        const now = Math.floor(Date.now() / 1000);
        if (payload.exp && payload.exp < now) {
            return null; // Expired
        }
        return payload;
    } catch {
        return null;
    }
}

// In-memory user cache pre-seeded with analyst & auditor
let users = {};
let sessions = [];

function initUsers() {
    if (fs.existsSync(USERS_FILE)) {
        try {
            users = JSON.parse(fs.readFileSync(USERS_FILE, 'utf-8'));
        } catch (err) {
            console.error('Warning: could not parse users file, reinitializing', err.message);
        }
    }

    // Default seeded users
    if (!users['analyst@sentinelvision.io']) {
        users['analyst@sentinelvision.io'] = {
            id: 'usr-analyst-001',
            email: 'analyst@sentinelvision.io',
            fullName: 'Security Analyst',
            role: 'ANALYST',
            passwordHash: hashPassword('Password123!'),
            createdAt: new Date().toISOString()
        };
    }
    if (!users['auditor@sentinelvision.io']) {
        users['auditor@sentinelvision.io'] = {
            id: 'usr-auditor-001',
            email: 'auditor@sentinelvision.io',
            fullName: 'Lead Auditor',
            role: 'AUDITOR',
            passwordHash: hashPassword('Password123!'),
            createdAt: new Date().toISOString()
        };
    }

    try {
        fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2), 'utf-8');
    } catch (err) {
        console.error('Could not save users file:', err.message);
    }
}

initUsers();

function saveUsers() {
    try {
        fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2), 'utf-8');
    } catch (err) {
        console.error('Could not save users file:', err.message);
    }
}

function login(email, password) {
    const user = users[email?.toLowerCase()?.trim()];
    if (!user) {
        const err = new Error('Invalid credentials');
        err.status = 401;
        throw err;
    }

    if (!verifyPassword(password, user.passwordHash)) {
        const err = new Error('Invalid credentials');
        err.status = 401;
        throw err;
    }

    const tokenPayload = {
        userId: user.id,
        email: user.email,
        role: user.role,
        fullName: user.fullName
    };
    const token = signJwt(tokenPayload);

    sessions.push({
        sessionId: `sess-${crypto.randomBytes(6).toString('hex')}`,
        userId: user.id,
        userName: user.fullName,
        userRole: user.role,
        loginAt: new Date().toISOString(),
        lastActivityAt: new Date().toISOString(),
        logoutAt: null,
        status: 'ACTIVE',
        ip: null,
        device: 'Electron Desktop'
    });

    return {
        token,
        user: {
            id: user.id,
            email: user.email,
            fullName: user.fullName,
            role: user.role
        }
    };
}

function register({ fullName, email, password, role = 'ANALYST' }) {
    const cleanEmail = email?.toLowerCase()?.trim();
    if (!cleanEmail || !password || !fullName) {
        const err = new Error('Full name, email, and password are required');
        err.status = 400;
        throw err;
    }

    if (users[cleanEmail]) {
        const err = new Error('Email already registered');
        err.status = 409;
        throw err;
    }

    const assignedRole = ['AUDITOR', 'ANALYST'].includes(role?.toUpperCase())
        ? role.toUpperCase()
        : 'ANALYST';

    const newUser = {
        id: `usr-${crypto.randomBytes(4).toString('hex')}`,
        email: cleanEmail,
        fullName: fullName.trim(),
        role: assignedRole,
        accountStatus: 'ACTIVE',
        passwordHash: hashPassword(password),
        createdAt: new Date().toISOString()
    };

    users[cleanEmail] = newUser;
    saveUsers();

    return {
        success: true,
        message: 'Registration successful',
        user: {
            id: newUser.id,
            email: newUser.email,
            fullName: newUser.fullName,
            role: newUser.role,
            accountStatus: newUser.accountStatus
        }
    };
}

function listUsers() {
    return Object.values(users).map(({ passwordHash, ...user }) => ({
        ...user,
        accountStatus: user.accountStatus || 'ACTIVE'
    }));
}

function setUserStatus(userId, status) {
    const user = Object.values(users).find((u) => u.id === userId);
    if (!user) { const err = new Error('User not found'); err.status = 404; throw err; }
    user.accountStatus = ['ACTIVE', 'SUSPENDED', 'PENDING'].includes(status) ? status : 'ACTIVE';
    saveUsers();
    return { ...user, passwordHash: undefined };
}

function approvePendingUser(userId) {
    return setUserStatus(userId, 'ACTIVE');
}

function listSessions() {
    return sessions.slice().reverse();
}

function requireAuth(req, res, next) {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
        return res.status(401).json({ error: 'Unauthorized: Missing or invalid token' });
    }

    const token = authHeader.slice(7).trim();
    const payload = verifyJwt(token);
    if (!payload) {
        return res.status(401).json({ error: 'Unauthorized: Session expired or invalid' });
    }

    req.user = payload;
    next();
}

function requireRole(allowedRoles = []) {
    return (req, res, next) => {
        if (!req.user) {
            return res.status(401).json({ error: 'Unauthorized' });
        }
        if (!allowedRoles.includes(req.user.role)) {
            return res.status(403).json({ error: `Forbidden: Requires one of [${allowedRoles.join(', ')}] role` });
        }
        next();
    };
}

module.exports = {
    login,
    register,
    verifyJwt,
    requireAuth,
    requireRole,
    listUsers,
    setUserStatus,
    approvePendingUser,
    listSessions
};
