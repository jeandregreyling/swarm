-- Add Mistral Vibe and Tiered Assistant to Hummingbird UI
-- Run this SQL against your swarm_hive.db to make them appear in the Support Team

-- 1. Add Mistral Vibe to agents table
INSERT OR IGNORE INTO agents (number, name, label, model, temperature, role, tier, enabled)
VALUES (
    22,
    'mistral-vibe',
    'Mistral Vibe',
    'mistral-large-latest',
    0.2,
    'Online teacher — teaches APEX system access patterns and complex reasoning',
    'online',
    1
);

-- 2. Add Tiered Assistant to agents table
INSERT OR IGNORE INTO agents (number, name, label, model, temperature, role, tier, enabled)
VALUES (
    23,
    'tiered-assistant',
    'Tiered Assistant',
    'tiered:fallback',
    0.2,
    'Online model fallback — assists APEX when local context is exhausted',
    'online',
    1
);

-- 3. Add Mistral Vibe to service principals (for peer bridge)
INSERT OR IGNORE INTO service_principals (id, display_name, role, enabled, created_at)
VALUES (
    'mistral-vibe',
    'Mistral Vibe',
    'service',
    1,
    strftime('%s', 'now')
);

-- 4. Add Tiered Assistant to service principals
INSERT OR IGNORE INTO service_principals (id, display_name, role, enabled, created_at)
VALUES (
    'tiered-assistant',
    'Tiered Model Assistant',
    'service',
    1,
    strftime('%s', 'now')
);

-- 5. Add scopes for Mistral Vibe
INSERT OR IGNORE INTO service_tokens (principal_id, token_sha256, scopes, created_at)
SELECT 
    'mistral-vibe',
    'placeholder_sha256',
    '{"scopes": ["peer.read", "peer.post", "peer.memory", "peer.relay:apex", "peer.relay:instructor"]}',
    strftime('%s', 'now')
WHERE NOT EXISTS (
    SELECT 1 FROM service_tokens WHERE principal_id = 'mistral-vibe'
);

-- 6. Add scopes for Tiered Assistant
INSERT OR IGNORE INTO service_tokens (principal_id, token_sha256, scopes, created_at)
SELECT 
    'tiered-assistant',
    'placeholder_sha256',
    '{"scopes": ["peer.read", "peer.post", "peer.memory", "peer.relay:apex"]}',
    strftime('%s', 'now')
WHERE NOT EXISTS (
    SELECT 1 FROM service_tokens WHERE principal_id = 'tiered-assistant'
);

-- 7. Update existing entries if they exist
UPDATE agents 
SET 
    label = 'Mistral Vibe',
    model = 'mistral-large-latest',
    temperature = 0.2,
    role = 'Online teacher — teaches APEX system access patterns and complex reasoning',
    tier = 'online',
    enabled = 1
WHERE name = 'mistral-vibe';

UPDATE agents 
SET 
    label = 'Tiered Assistant',
    model = 'tiered:fallback',
    temperature = 0.2,
    role = 'Online model fallback — assists APEX when local context is exhausted',
    tier = 'online',
    enabled = 1
WHERE name = 'tiered-assistant';

-- 8. Verify the entries
SELECT * FROM agents WHERE name IN ('mistral-vibe', 'tiered-assistant');
SELECT * FROM service_principals WHERE id IN ('mistral-vibe', 'tiered-assistant');
