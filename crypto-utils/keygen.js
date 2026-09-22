#!/usr/bin/env node
/**
 * Node.js Ed25519 Key Generation Utility for SentinelVision.
 * Generates Ed25519 keypairs for named module identities using Node crypto.
 * Compatible with PyNaCl keypairs and public_key_registry.json.
 */
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const DEFAULT_KEY_DIR = path.join(__dirname, 'keys');
const REGISTRY_PATH = path.join(__dirname, 'public_key_registry.json');

function generateKeypair(moduleName, keyDir = DEFAULT_KEY_DIR, registryPath = REGISTRY_PATH) {
  if (!fs.existsSync(keyDir)) {
    fs.mkdirSync(keyDir, { recursive: true });
  }

  const { privateKey, publicKey } = crypto.generateKeyPairSync('ed25519');

  const privDer = privateKey.export({ format: 'der', type: 'pkcs8' });
  const privSeedHex = privDer.subarray(-32).toString('hex');

  const pubDer = publicKey.export({ format: 'der', type: 'spki' });
  const pubHex = pubDer.subarray(-32).toString('hex');

  const privPath = path.join(keyDir, `${moduleName}.priv`);
  fs.writeFileSync(privPath, privSeedHex + '\n', { mode: 0o600 });

  let registry = {};
  if (fs.existsSync(registryPath)) {
    try {
      registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
    } catch (e) {
      registry = {};
    }
  }

  registry[moduleName] = pubHex;
  fs.writeFileSync(registryPath, JSON.stringify(registry, Object.keys(registry).sort(), 2) + '\n');

  return { privPath, pubHex };
}

if (require.main === module) {
  const args = process.argv.slice(2).filter(a => !a.startsWith('-'));
  const targets = args.length > 0 ? args : ['ModelIntegrity', 'InferenceProvenance'];
  for (const id of targets) {
    const { privPath, pubHex } = generateKeypair(id);
    console.log(`[${id}] Private key: ${privPath}`);
    console.log(`[${id}] Public key:  ${pubHex}`);
  }
}

module.exports = { generateKeypair };
