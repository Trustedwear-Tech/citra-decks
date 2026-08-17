// Copyright (c) 2026 Trustedwear Tech Private Limited (https://citra-ai.com)
// Author: Rohit Kumar Chandan
// SPDX-License-Identifier: BUSL-1.1
//
// Licensed under the Business Source License 1.1. Non-production use is granted;
// production use requires a commercial licence until the Change Date, after
// which this file converts to Apache-2.0. See LICENSE at the repository root.

const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');
const { URL } = require('url');

function getClient(url) {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' ? http : https;
}

function env(name, defaultValue = null) {
    const value = process.env[name];
    return (value !== undefined && value !== '') ? value : defaultValue;
}

function splitKv2Path(secretPath) {
    const p = secretPath.trim().replace(/^\/+|\/+$/g, '');
    if (!p.includes('/')) {
        throw new Error("VAULT_SECRET_PATH must be '<mount>/<name>', e.g. 'env/citra-ai'");
    }
    return p.split('/', 2);
}

function vaultSession(timeout) {
    return {
        timeout: timeout,
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    };
}

async function approleLogin(vaultAddr, roleId, secretId, timeout) {
    const url = `${vaultAddr.replace(/\/$/, '')}/v1/auth/approle/login`;

    const postData = JSON.stringify({
        role_id: roleId,
        secret_id: secretId
    });

    return new Promise((resolve, reject) => {
        const client = getClient(url);
        const req = client.request(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData)
            },
            timeout: timeout * 1000
        }, (res) => {
            let data = '';
            res.on('data', (chunk) => data += chunk);
            res.on('end', () => {
                if (res.statusCode !== 200) {
                    reject(new Error(`AppRole login failed: HTTP ${res.statusCode} ${data}`));
                    return;
                }
                try {
                    const response = JSON.parse(data);
                    const token = response.auth?.client_token;
                    if (!token) {
                        reject(new Error('AppRole login succeeded but no client_token in response'));
                    } else {
                        resolve(token);
                    }
                } catch (e) {
                    reject(new Error(`Failed to parse login response: ${e.message}`));
                }
            });
        });

        req.on('error', (e) => reject(e));
        req.on('timeout', () => {
            req.destroy();
            reject(new Error('Request timeout'));
        });

        req.write(postData);
        req.end();
    });
}

async function kv2Read(vaultAddr, token, mount, name, timeout) {
    const url = `${vaultAddr.replace(/\/$/, '')}/v1/${mount}/data/${name}`;

    return new Promise((resolve, reject) => {
        const client = getClient(url);
        const req = client.request(url, {
            method: 'GET',
            headers: {
                'X-Vault-Token': token,
                'Accept': 'application/json'
            },
            timeout: timeout * 1000
        }, (res) => {
            let data = '';
            res.on('data', (chunk) => data += chunk);
            res.on('end', () => {
                if (res.statusCode === 200) {
                    try {
                        const payload = JSON.parse(data);
                        const secrets = payload.data?.data || {};
                        resolve(secrets);
                    } catch (e) {
                        reject(new Error(`Failed to parse KV response: ${e.message}`));
                    }
                } else if (res.statusCode === 403 || res.statusCode === 404) {
                    console.warn(`Vault KV read not permitted or not found (HTTP ${res.statusCode}). If this is a write-only account, reads are intentionally blocked.`);
                    resolve({});
                } else {
                    reject(new Error(`KV read failed: HTTP ${res.statusCode} ${data}`));
                }
            });
        });

        req.on('error', (e) => reject(e));
        req.on('timeout', () => {
            req.destroy();
            reject(new Error('Request timeout'));
        });

        req.end();
    });
}

async function loadEnvironmentVariables() {
    // 1) Load .env file (dev overrides)
    const envPath = path.join(__dirname, '.env');
    if (fs.existsSync(envPath)) {
        require('dotenv').config({ path: envPath });
        console.log('✅ Loaded local .env file');
    } else {
        console.log('ℹ️ No .env file found');
    }

    // 2) Vault config
    const vaultAddr = env('VAULT_ADDR');
    let vaultToken = env('VAULT_TOKEN');
    const roleId = env('VAULT_ROLE_ID');
    const secretId = env('VAULT_SECRET_ID');
    const secretPath = env('VAULT_SECRET_PATH', 'env/citra-ai');
    const timeout = parseFloat(env('VAULT_TIMEOUT', '10'));

    if (!vaultAddr) {
        console.log('🔧 VAULT_ADDR not set — using .env only');
        return {};
    }

    // 3) Get a token (token or AppRole)
    if (!vaultToken) {
        if (roleId && secretId) {
            console.log('🔐 Logging into Vault with AppRole');
            try {
                vaultToken = await approleLogin(vaultAddr, roleId, secretId, timeout);
                console.log('🔐 AppRole login successful (received client token)');
            } catch (e) {
                console.error('❌ AppRole login failed:', e.message);
                throw e;
            }
        } else {
            console.log('🔧 Vault configured without VAULT_TOKEN or VAULT_ROLE_ID/VAULT_SECRET_ID — skipping');
            return {};
        }
    }

    // 4) Health + token sanity (best-effort)
    try {
        const healthUrl = `${vaultAddr.replace(/\/$/, '')}/v1/sys/health`;
        await new Promise((resolve, reject) => {
            const client = getClient(healthUrl);
            const req = client.request(healthUrl, { timeout: timeout * 1000 }, (res) => {
                if (res.statusCode === 200 || res.statusCode === 429) {
                    resolve();
                } else {
                    console.warn(`⚠️ Vault health not OK (HTTP ${res.statusCode})`);
                    resolve(); // Don't fail on health check
                }
            });
            req.on('error', () => resolve()); // Don't fail on health check
            req.on('timeout', () => resolve()); // Don't fail on health check
            req.end();
        });
    } catch (e) {
        console.warn(`⚠️ Could not check Vault health: ${e.message}`);
    }

    // 5) Resolve KV v2 mount/name and read
    try {
        const [mount, name] = splitKv2Path(secretPath);
        console.log(`📦 Fetching KV v2 secret at ${secretPath} (mount=${mount}, name=${name})`);

        const secrets = await kv2Read(vaultAddr, vaultToken, mount, name, timeout);

        if (Object.keys(secrets).length > 0) {
            for (const [k, v] of Object.entries(secrets)) {
                process.env[k] = String(v);
            }
            console.log(`✅ Loaded ${Object.keys(secrets).length} Vault secrets from ${secretPath}`);
        } else {
            console.log('ℹ️ No secrets loaded from Vault (read not permitted or secret missing).');
        }

        return secrets;
    } catch (e) {
        if (e.code === 'ENOTFOUND' || e.code === 'ECONNREFUSED') {
            console.error('❌ Vault connection error:', e.message);
        } else {
            console.error('❌ Failed to load Vault secrets:', e.message);
        }
        throw e;
    }
}

module.exports = { loadEnvironmentVariables };