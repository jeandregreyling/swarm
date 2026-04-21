"""auth.py — Auth & Senders routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

auth_bp = Blueprint('auth', __name__)

def _get_sender_lists():
    conn = get_connection()
    try:
        trusted = [dict(r) for r in conn.execute(
            "SELECT id, email, added_by, notes, added_at FROM trusted_senders ORDER BY added_at DESC"
        ).fetchall()]
        notification = [dict(r) for r in conn.execute(
            "SELECT id, email, added_by, notes, added_at FROM notification_senders ORDER BY added_at DESC"
        ).fetchall()]
        domains = [dict(r) for r in conn.execute(
            "SELECT id, domain, channel, added_by, notes, added_at FROM trusted_domains ORDER BY added_at DESC"
        ).fetchall()]
        return {'trusted': trusted, 'notification': notification, 'domains': domains}
    finally:
        conn.close()



@auth_bp.route('/api/senders')
def api_senders():
    return jsonify(_get_sender_lists())



@auth_bp.route('/api/senders', methods=['POST'])
def add_sender():
    from database import add_trusted_domain
    data    = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'senders_add')
    if gate:
        return gate
    lst     = data.get('list', '')
    address = (data.get('address') or '').strip().lower()
    note    = (data.get('note') or '').strip()
    channel = (data.get('channel') or 'email').strip().lower()
    if not address or lst not in ('trusted', 'notification', 'domain'):
        return jsonify({'error': 'invalid'}), 400
    if lst == 'trusted':
        add_trusted_sender(address, added_by='dashboard', note=note)
    elif lst == 'domain':
        add_trusted_domain(address.lstrip('@'), added_by='dashboard', note=note, channel=channel)
    else:
        add_notification_sender(address, added_by='dashboard', note=note)
    print(f'[Terminal] Added {address} to {lst}')
    return jsonify({'ok': True, 'list': lst, 'address': address})



@auth_bp.route('/api/senders', methods=['DELETE'])
def remove_sender():
    data    = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'senders_remove')
    if gate:
        return gate
    lst     = data.get('list', '')
    address = (data.get('address') or '').strip().lower()
    if not address or lst not in ('trusted', 'notification', 'domain'):
        return jsonify({'error': 'invalid'}), 400
    if lst == 'trusted':
        remove_trusted_sender(address)
    elif lst == 'domain':
        conn = get_connection()
        conn.execute("DELETE FROM trusted_domains WHERE LOWER(domain)=?", (address.lstrip('@'),))
        conn.commit()
        conn.close()
    else:
        remove_notification_sender(address)
    print(f'[Terminal] Removed {address} from {lst}')
    return jsonify({'ok': True, 'list': lst, 'address': address})



@auth_bp.route('/api/access/manager/onboard', methods=['POST'])
def api_manager_onboard():
    """
    Onboard a second trusted user (manager) using Fridays trust model.
    Body:
      {
        "manager_email": "manager@company.com",        # required
        "manager_name": "Manager",                     # optional
        "manager_telegram_chat_id": "123456789",      # optional
        "add_as_moderator": false,                      # optional
        "dry_run": true,                                # optional (default true)
        "proposal_id": "..."                           # required when dry_run=false and Time Wizard active
      }
    """
    data = request.get_json() or {}
    manager_email = (data.get('manager_email') or '').strip().lower()
    manager_name = (data.get('manager_name') or 'Manager').strip() or 'Manager'
    manager_telegram_chat_id = str(data.get('manager_telegram_chat_id') or '').strip()
    add_as_moderator = bool(data.get('add_as_moderator', False))
    dry_run = bool(data.get('dry_run', True))

    if not manager_email or '@' not in manager_email:
        return jsonify({'ok': False, 'error': 'manager_email required'}), 400

    if manager_telegram_chat_id and not manager_telegram_chat_id.isdigit():
        return jsonify({'ok': False, 'error': 'manager_telegram_chat_id must be numeric'}), 400

    if not dry_run:
        gate = _alm_gate_or_response(data, 'manager_onboard')
        if gate:
            return gate

    trusted_entries = [manager_email]
    if manager_telegram_chat_id:
        trusted_entries.append(f'telegram:{manager_telegram_chat_id}')

    plan = {
        'manager_email': manager_email,
        'manager_name': manager_name,
        'add_as_moderator': add_as_moderator,
        'trusted_entries_to_add': trusted_entries,
        'moderator_entry_to_add': manager_email if add_as_moderator else None,
        'tailscale_step_required': True,
        'tailscale_note': 'Grant manager Tailscale access separately; API does not manage Tailscale identities.',
    }

    if dry_run:
        return jsonify({'ok': True, 'dry_run': True, 'plan': plan})

    results = []
    try:
        add_trusted_sender(manager_email, added_by='dashboard', note=f'Manager onboarding: {manager_name}')
        results.append({'action': 'trusted_sender_add', 'entry': manager_email, 'status': 'ok'})
    except Exception as e:
        if 'UNIQUE' in str(e).upper():
            results.append({'action': 'trusted_sender_add', 'entry': manager_email, 'status': 'exists'})
        else:
            return jsonify({'ok': False, 'error': f'failed to add manager email: {e}', 'results': results}), 500

    if manager_telegram_chat_id:
        tg_entry = f'telegram:{manager_telegram_chat_id}'
        try:
            add_trusted_sender(tg_entry, added_by='dashboard', note=f'Manager onboarding: {manager_name}')
            results.append({'action': 'trusted_sender_add', 'entry': tg_entry, 'status': 'ok'})
        except Exception as e:
            if 'UNIQUE' in str(e).upper():
                results.append({'action': 'trusted_sender_add', 'entry': tg_entry, 'status': 'exists'})
            else:
                return jsonify({'ok': False, 'error': f'failed to add manager telegram: {e}', 'results': results}), 500

    if add_as_moderator:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO moderators (email, name, notes) VALUES (?, ?, ?)",
                (manager_email, manager_name, 'Added via manager onboarding API')
            )
            conn.commit()
            results.append({'action': 'moderator_add', 'entry': manager_email, 'status': 'ok'})
        except Exception as e:
            conn.rollback()
            return jsonify({'ok': False, 'error': f'failed to add moderator: {e}', 'results': results}), 500
        finally:
            conn.close()

    log_activity('terminal', 'manager_onboard', f'email={manager_email} tg={manager_telegram_chat_id or "none"}')
    return jsonify({
        'ok': True,
        'dry_run': False,
        'plan': plan,
        'results': results,
    }), 201



@auth_bp.route('/api/skills/available')
def api_skills_available():
    from fridays.skills import list_skills
    return jsonify(list_skills())



@auth_bp.route('/api/auth/profiles')
def api_auth_profiles():
    include_inactive = request.args.get('include_inactive', '0') in ('1', 'true', 'yes')
    return jsonify({'ok': True, 'profiles': list_user_profiles(include_inactive=include_inactive)})



@auth_bp.route('/api/auth/context')
def api_auth_context():
    data = {
        'acting_user': request.args.get('acting_user', 'ghost'),
        'proxy_as': request.args.get('proxy_as', ''),
    }
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err

    return jsonify({
        'ok': True,
        'identity': {
            'acting_user': identity['acting_user'],
            'proxy_as': identity['proxy_as'],
            'effective_user': identity['effective_user'],
            'can_proxy': identity['can_proxy'],
        },
        'effective_profile': identity['effective'],
    })



@auth_bp.route('/api/auth/profiles', methods=['POST'])
def api_auth_profiles_create():
    data = request.get_json() or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err
    if identity['acting_user'] != 'ghost':
        return jsonify({'ok': False, 'error': 'only ghost can create profiles'}), 403

    username = (data.get('username') or '').strip().lower()
    display_name = (data.get('display_name') or username).strip()
    user_type = (data.get('user_type') or 'human').strip().lower()
    linked_agent = (data.get('linked_agent') or '').strip().lower()
    is_active = bool(data.get('is_active', True))
    can_proxy = bool(data.get('can_proxy', False))
    if not username:
        return jsonify({'ok': False, 'error': 'username required'}), 400

    profile = upsert_user_profile(
        username=username,
        display_name=display_name,
        user_type=user_type,
        linked_agent=linked_agent,
        is_active=1 if is_active else 0,
        can_proxy=1 if can_proxy else 0,
        created_by='ghost',
    )
    log_activity('terminal', 'profile_created', f'{username} by ghost')
    return jsonify({'ok': True, 'profile': profile}), 201



@auth_bp.route('/api/auth/profiles/<username>', methods=['PATCH'])
def api_auth_profiles_patch(username):
    data = request.get_json() or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err
    if identity['acting_user'] != 'ghost':
        return jsonify({'ok': False, 'error': 'only ghost can update profiles'}), 403

    existing = get_user_profile(username)
    if not existing:
        return jsonify({'ok': False, 'error': 'profile not found'}), 404

    updated = upsert_user_profile(
        username=username,
        display_name=data.get('display_name', existing.get('display_name') or username),
        user_type=data.get('user_type', existing.get('user_type') or 'human'),
        linked_agent=data.get('linked_agent', existing.get('linked_agent') or ''),
        is_active=bool(data.get('is_active', bool(existing.get('is_active')))),
        can_proxy=bool(data.get('can_proxy', bool(existing.get('can_proxy')))),
        created_by='ghost',
    )
    log_activity('terminal', 'profile_updated', f'{username} by ghost')
    return jsonify({'ok': True, 'profile': updated})



@auth_bp.route('/api/skills/permissions')
def api_skills_permissions():
    username = (request.args.get('username') or request.args.get('user') or '').strip().lower()
    if not username:
        return jsonify({'ok': False, 'error': 'username required'}), 400
    profile = get_user_profile(username)
    if not profile:
        return jsonify({'ok': False, 'error': 'profile not found'}), 404
    return jsonify({
        'ok': True,
        'username': username,
        'permissions': list_user_skill_permissions(username),
    })



@auth_bp.route('/api/skills/permissions', methods=['POST'])
def api_skills_permissions_update():
    data = request.get_json() or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err
    if identity['acting_user'] != 'ghost':
        return jsonify({'ok': False, 'error': 'only ghost can update permissions'}), 403

    username = (data.get('username') or '').strip().lower()
    skill_name = (data.get('skill_name') or data.get('skill') or '').strip().lower()
    allowed = bool(data.get('allowed', True))
    if not username or not skill_name:
        return jsonify({'ok': False, 'error': 'username and skill_name required'}), 400
    if not get_user_profile(username):
        return jsonify({'ok': False, 'error': 'profile not found'}), 404

    set_user_skill_permission(username, skill_name, allowed=allowed, created_by='ghost')
    log_activity('terminal', 'skill_permission_updated', f'{username}:{skill_name}={"allow" if allowed else "deny"}')
    return jsonify({
        'ok': True,
        'username': username,
        'permissions': list_user_skill_permissions(username),
    })



@auth_bp.route('/api/skills/run', methods=['POST'])
def api_skills_run():
    data = request.get_json() or {}
    skill_name = (data.get('skill') or '').strip().lower()
    args       = (data.get('args')  or '').strip()

    identity, err = _resolve_identity_or_response(data)
    if err:
        return err

    if not skill_name:
        return jsonify({'error': 'skill name required'}), 400
    from fridays.skills import call as skill_call, REGISTRY as SKILL_REGISTRY
    meta = SKILL_REGISTRY.get(skill_name)
    if not meta:
        known = ', '.join(sorted(SKILL_REGISTRY.keys()))
        return jsonify({'ok': False, 'error': f"Unknown skill: {skill_name!r}. Known skills: {known}"}), 400

    effective_user = identity['effective_user']
    if not can_user_invoke_skill(effective_user, skill_name, default_allow=True):
        return jsonify({'ok': False, 'error': f'user {effective_user} is not authorized for skill {skill_name}'}), 403

    trust_level = int(meta.get('trust_level', 0) or 0)
    if trust_level >= 1:
        gate = _alm_gate_or_response(data, f'skills_run_{skill_name}')
        if gate:
            return gate

    ok, output = skill_call(skill_name, args=args, agent=effective_user)
    return jsonify({'ok': ok, 'output': output, 'identity': {
        'acting_user': identity['acting_user'],
        'proxy_as': identity['proxy_as'],
        'effective_user': effective_user,
    }})



