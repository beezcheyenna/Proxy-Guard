const MAX_BODY = 24576;
const MAX_RESPONSE = 32768;
const enc = new TextEncoder();
const reply = (data, status = 200) => Response.json(data, { status, headers: {
  'cache-control': 'no-store', 'x-content-type-options': 'nosniff'
}});
function equal(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  let difference = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++)
    difference |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return difference === 0;
}
export function publicIP(value) {
  if (typeof value !== 'string' || value.length > 45) throw new Error('invalid_source_ip');
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(value)) {
    const a = value.split('.').map(Number);
    if (a.some((n, i) => n > 255 || String(n) !== value.split('.')[i]) ||
        a[0] === 0 || a[0] === 10 || a[0] === 127 || a[0] >= 224 ||
        (a[0] === 100 && a[1] >= 64 && a[1] <= 127) ||
        (a[0] === 169 && a[1] === 254) || (a[0] === 172 && a[1] >= 16 && a[1] <= 31) ||
        (a[0] === 192 && (a[1] === 168 || (a[1] === 0 && (a[2] === 0 || a[2] === 2)))) ||
        (a[0] === 198 && (a[1] === 18 || a[1] === 19 || (a[1] === 51 && a[2] === 100))) ||
        (a[0] === 203 && a[1] === 0 && a[2] === 113)) throw new Error('invalid_source_ip');
    return value;
  }
  if (!/^[a-fA-F0-9:]+$/.test(value)) throw new Error('invalid_source_ip');
  let ip;
  try { ip = new URL('http://[' + value + ']/').hostname.slice(1, -1).toLowerCase(); }
  catch { throw new Error('invalid_source_ip'); }
  const first = Number.parseInt(ip.split(':')[0], 16);
  if (!(first >= 0x2000 && first <= 0x3fff) || ip.startsWith('2001:db8:') ||
      ip === '2a06:98c0:3600::103') throw new Error('invalid_source_ip');
  return ip;
}
function credentials(env, request) {
  if ((env.DEVICE_TOKEN || '').startsWith('REPLACE_') || (env.AGENT_SECRET || '').startsWith('REPLACE_') ||
      !/^[A-Za-z0-9_-]{32,256}$/.test(env.DEVICE_TOKEN || '') ||
      !/^[A-Za-z0-9_-]{32,256}$/.test(env.AGENT_SECRET || '') ||
      !/^[a-zA-Z0-9_-]{1,64}$/.test(env.DEVICE_ID || '') || equal(env.DEVICE_TOKEN, env.AGENT_SECRET))
    return reply({ ok: false, code: 'not_configured' }, 503);
  if (!equal(request.headers.get('authorization'), 'Bearer ' + env.DEVICE_TOKEN))
    return reply({ ok: false, code: 'unauthorized' }, 401);
  // Workers-originated subrequests are not a direct household-IP observation.
  if (request.headers.has('cf-worker'))
    return reply({ ok: false, code: 'direct_connection_required' }, 403);
}
export async function sign(secret, body) {
  const key = await crypto.subtle.importKey('raw', enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return [...new Uint8Array(await crypto.subtle.sign('HMAC', key, enc.encode(body)))]
    .map(x => x.toString(16).padStart(2, '0')).join('');
}
async function readBounded(request, limit = MAX_BODY) {
  const size = Number(request.headers.get('content-length'));
  if (size > limit) throw new Error('body_too_large');
  if (!request.body) throw new Error('invalid_request');
  const reader = request.body.getReader(); let bytes = 0; const chunks = [];
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > limit) throw new Error('body_too_large');
      chunks.push(value);
    }
  } finally { await reader.cancel().catch(() => {}); }
  const joined = new Uint8Array(bytes); let pos = 0;
  for (const chunk of chunks) { joined.set(chunk, pos); pos += chunk.length; }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(joined));
}
// Export only the fields needed by the Pro client. Unknown backend fields must
// not silently become a Cloudflare data export after an Agent upgrade.
const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const pick = (v, keys) => Object.fromEntries(keys.filter(k => v?.[k] !== undefined).map(k => [k,v[k]]));
const sshPublic = v => pick(v, ['managed','confirmed','port','rescue_enabled','after','scope','open_seconds']);
function policyPublic(v) {
  if (!object(v) || typeof v.enabled !== 'boolean' || !['standard','whitelist','observe'].includes(v.mode) ||
      !Array.isArray(v.address_families) || !v.address_families.length || v.address_families.some(x=>x!==4&&x!==6) || !object(v.ssh))
    throw new Error('invalid_agent_response');
  const out={...pick(v,['enabled','default_deny','auto_discover','address_families','mode','scope','outbound_replies_preserved']),ssh:sshPublic(v.ssh)};
  if(v.per_rule_modes!==undefined || v.rule_modes!==undefined) {
    if(v.per_rule_modes!==true || !object(v.rule_modes) || Object.keys(v.rule_modes).length>32 ||
       Object.entries(v.rule_modes).some(([id,mode])=>!(/^[A-Za-z0-9_-]{1,32}$/.test(id)) || !['standard','whitelist','observe'].includes(mode)))
      throw new Error('invalid_agent_response');
    out.per_rule_modes=true;out.rule_modes=Object.fromEntries(Object.entries(v.rule_modes));
  }
  if(v.policy_confirmation!==undefined){if(v.policy_confirmation!==true)throw new Error('invalid_agent_response');out.policy_confirmation=true;}
  if(v.source_modes_v2!==undefined || v.rule_effects!==undefined){
    if(v.source_modes_v2!==true || !object(v.rule_effects) || Object.keys(v.rule_effects).length>32 ||
       Object.entries(v.rule_effects).some(([id,effect])=>!(/^[A-Za-z0-9_-]{1,32}$/.test(id)) || !['standard','whitelist','observe','bypass','disabled'].includes(effect)))
      throw new Error('invalid_agent_response');
    out.source_modes_v2=true;out.rule_effects=Object.fromEntries(Object.entries(v.rule_effects));
  }
  return out;
}
function trialPublic(v){
  if(!object(v)||v.supported!==true||!['idle','applying','confirming','restoring','confirmed','rolled_back','conflict'].includes(v.phase))throw new Error('invalid_agent_response');
  if(v.phase==='idle')return {supported:true,phase:'idle'};
  if(!uuid(v.id)||!Number.isSafeInteger(v.revision)||v.revision<1||!Number.isInteger(v.remaining)||v.remaining<0||v.remaining>300)throw new Error('invalid_agent_response');
  const out=pick(v,['supported','id','phase','revision','remaining']);
  if(['unchanged_policy','user_confirmed','user_cancelled','confirmation_timeout','restart_before_confirmation','apply_failed','policy_changed'].includes(v.reason))out.reason=v.reason;
  return out;
}
const phases = ['accepted','dispatching','verifying','complete','failed','indeterminate'];
const uuid = v => typeof v === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(v);
const operationErrors = ['interrupted_operation_not_repeated','policy_changed_before_dispatch','maintenance_dispatch_failed','recovery_not_verified'];
function operationPublic(v) {
  if (!object(v) || !uuid(v.operation_id) || !['restart_xray','reboot_vps'].includes(v.action) || !phases.includes(v.phase))
    throw new Error('invalid_agent_response');
  const out=pick(v,['operation_id','action','phase','created_at','completed_at','revision']);
  if (operationErrors.includes(v.error)) out.error=v.error;
  return out;
}
function statusPublic(v) {
  if (!object(v) || v.ok !== true || v.protocol !== 3 || v.edition !== 'pro' || typeof v.agent_ready !== 'boolean' ||
      !Number.isSafeInteger(v.revision) || v.revision < 0 || !object(v.health) || !object(v.leases) ||
      typeof v.health.configured !== 'boolean' || typeof v.health.ok !== 'boolean' || typeof v.health.stale !== 'boolean')
    throw new Error('invalid_agent_response');
  const health=pick(v.health,['configured','ok','stale','checked_at','interval']);
  health.services=(Array.isArray(v.health.services)?v.health.services:[]).map(x=>pick(x,['name','ok','required']));
  const leases={};
  for(const family of ['4','6']) if(object(v.leases[family]) && Number.isSafeInteger(v.leases[family].expires_in) && v.leases[family].expires_in>=0)
    leases[family]={expires_in:v.leases[family].expires_in};
  const out={ok:true,protocol:3,edition:'pro',agent_ready:v.agent_ready,revision:v.revision,health,leases,
    ingress:policyPublic(v.ingress),analysis_exported:false};
  if(v.policy_trial!==undefined)out.policy_trial=trialPublic(v.policy_trial);
  if(object(v.firewall))out.firewall=pick(v.firewall,['verified','packets_dropped','bytes_dropped']);
  if(object(v.ssh_rescue))out.ssh_rescue=pick(v.ssh_rescue,['managed','armed','port','rescue_enabled','scope','effective_scope','emergency','public_remaining','control_age','proxy_age','system_firewall_still_applies']);
  if(object(v.maintenance))out.maintenance={...pick(v.maintenance,['enabled','allow_restart_xray','allow_reboot','adapter']),
    state_error:v.maintenance.state_error==='operation_state_unavailable'?'operation_state_unavailable':null,
    operations:(Array.isArray(v.maintenance.operations)?v.maintenance.operations:[]).map(operationPublic)};
  if(object(v.resources))out.resources={...pick(v.resources,['bandwidth_requested','access_log_available','fallback_telemetry_available']),
    details_exported:false,native_checks:pick(v.resources.native_checks,['configured','ok'])};
  return out;
}
const egressWarnings = new Set(['non_public_ipv4_omitted','no_public_ipv4_candidate','interface_unavailable',
  'panel_unavailable','panel_hint_unverified','panel_hint_ignored','measurement_disabled','measurement_pending',
  'measurement_failed','measurement_stale','measurement_disagreement','multiple_public_ipv4_candidates',
  'host_default_not_business_egress','candidates_truncated']);
const egressScopes = {interface:'host_interface',panel:'panel_config',measured:'host_default_ipv4'};
const epoch = v => Number.isSafeInteger(v) && v >= 0;
function egressPublic(v) {
  const invalid = () => {throw new Error('invalid_agent_response');};
  if (!object(v) || v.ok!==true || v.protocol!==3 || v.egress_info_schema!==1 || !epoch(v.generated_at) ||
      !['available','partial','unavailable'].includes(v.status) || typeof v.ambiguous!=='boolean' ||
      v.business_egress_verified!==false || !Array.isArray(v.candidates) || v.candidates.length>8 ||
      !Array.isArray(v.warnings) || v.warnings.length>16 || v.warnings.some(x=>!egressWarnings.has(x)) ||
      !object(v.measurement) || !['disabled','pending','fresh','stale','unavailable','conflict'].includes(v.measurement.state) ||
      !(v.measurement.checked_at===null || epoch(v.measurement.checked_at)) || typeof v.measurement.stale!=='boolean') invalid();
  const ips=new Set();
  const candidates=v.candidates.map(candidate=>{
    if (!object(candidate) || typeof candidate.ipv4!=='string' || candidate.ipv4.includes(':') ||
        candidate.ipv4.startsWith('192.88.99.') || !Array.isArray(candidate.evidence) ||
        !candidate.evidence.length || candidate.evidence.length>3) invalid();
    let ip;try {ip=publicIP(candidate.ipv4);}catch {invalid();}
    if (ips.has(ip)) invalid();ips.add(ip);
    const seen=new Set();
    const evidence=candidate.evidence.map(row=>{
      if (!object(row) || typeof row.source!=='string' || !Object.hasOwn(egressScopes,row.source) || seen.has(row.source) ||
          row.scope!==egressScopes[row.source] || !epoch(row.checked_at)) invalid();
      seen.add(row.source);return pick(row,['source','checked_at','scope']);
    });
    return {ipv4:ip,evidence};
  });
  if ((candidates.length>1 && !v.ambiguous) || (!candidates.length && v.status!=='unavailable')) invalid();
  return {ok:true,protocol:3,egress_info_schema:1,generated_at:v.generated_at,status:v.status,candidates,
    ambiguous:v.ambiguous,business_egress_verified:false,warnings:[...new Set(v.warnings)],
    measurement:pick(v.measurement,['state','checked_at','stale'])};
}
async function agentJSON(response) {
  try {return await readBounded(response,MAX_RESPONSE);}
  catch(error) {throw new Error(error.message==='body_too_large'?'response_limit':'invalid_agent_response');}
}
const commandDenials = new Set(['operation_or_authentication_denied','operation_busy','operation_cooldown','expired_operation',
  'xui_usr1_not_confirmed','invalid_revision','invalid_operation_id','operation_id_conflict','unsupported_action']);
export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);
      if (url.protocol !== 'https:') return reply({ ok: false, code: 'https_required' }, 400);
      if (url.search) return reply({ ok: false, code: 'invalid_request' }, 400);
      const denied = credentials(env, request); if (denied) return denied;
      const observed = publicIP(request.headers.get('cf-connecting-ip'));
      if (url.pathname === '/v1/observe' && request.method === 'GET')
        return reply({ ok: true, observed_ip: observed, family: observed.includes(':') ? 6 : 4 });
      if (url.pathname !== '/v1/sync' && url.pathname !== '/v1/status' && url.pathname !== '/v1/command' && url.pathname !== '/v1/egress-info' && url.pathname !== '/v1/policy-confirm' && url.pathname !== '/v1/policy-cancel')
        return reply({ ok: false, code: 'not_found' }, 404);
      if (request.method !== 'POST') return reply({ ok: false, code: 'method_not_allowed' }, 405);
      if ((request.headers.get('content-type') || '').split(';')[0].trim().toLowerCase() !== 'application/json')
        return reply({ ok: false, code: 'json_required' }, 415);
      const input = await readBounded(request);
      if (!object(input) || (input.device_id !== undefined && input.device_id !== env.DEVICE_ID))
        return reply({ok:false,code:'invalid_request'},400);
      if (url.pathname !== '/v1/sync' && (!env.VPS_API || typeof env.VPS_API.fetch !== 'function'))
        return reply({ok:false,code:'vpc_not_configured'},503);
      if (url.pathname === '/v1/egress-info') {
        if (input.device_id!==env.DEVICE_ID || Object.keys(input).some(k=>k!=='device_id'))
          return reply({ok:false,code:'invalid_request'},400);
        const payload=JSON.stringify({device_id:env.DEVICE_ID,issued_at:Date.now(),request_id:crypto.randomUUID(),purpose:'egress-info'});
        const signature=await sign(env.AGENT_SECRET,payload);
        let upstream;
        try {
          upstream=await env.VPS_API.fetch('http://vps-agent.internal/v1/egress-info',{
            method:'POST',redirect:'manual',signal:AbortSignal.timeout(8000),
            headers:{'content-type':'application/json','x-pg-signature':signature},body:payload});
        } catch {return reply({ok:false,code:'vpc_unavailable'},502);}
        if ([404,501].includes(upstream.status)) {
          await upstream.body?.cancel().catch(()=>{});return reply({ok:false,code:'egress_info_unsupported'},501);
        }
        if (!upstream.ok) {
          await upstream.body?.cancel().catch(()=>{});return reply({ok:false,code:'egress_info_unavailable'},502);
        }
        return reply(egressPublic(await agentJSON(upstream)));
      }
      if(['/v1/policy-confirm','/v1/policy-cancel'].includes(url.pathname)){
        if(!uuid(input.trial_id)||!Number.isSafeInteger(input.revision)||input.revision<1||Object.keys(input).some(k=>!['device_id','trial_id','revision'].includes(k)))return reply({ok:false,code:'invalid_request'},400);
        const payload=JSON.stringify({device_id:env.DEVICE_ID,trial_id:input.trial_id,revision:input.revision,issued_at:Date.now(),request_id:crypto.randomUUID()});
        const signature=await sign(env.AGENT_SECRET,payload);let response;
        try{response=await env.VPS_API.fetch('http://vps-agent.internal'+url.pathname,{method:'POST',redirect:'manual',signal:AbortSignal.timeout(8000),headers:{'content-type':'application/json','x-pg-signature':signature},body:payload});}
        catch{return reply({ok:false,code:'policy_trial_result_unknown'},502);}
        if(!response.ok){await response.body?.cancel().catch(()=>{});return reply({ok:false,code:response.status>=500?'policy_trial_result_unknown':'policy_trial_rejected'},response.status>=500?502:409);}
        const result=await agentJSON(response);if(result.ok!==true)throw new Error('invalid_agent_response');
        return reply({ok:true,policy_trial:trialPublic(result.policy_trial)});
      }
      if (url.pathname === '/v1/command') {
        if (!input || !['restart_xray','reboot_vps'].includes(input.action) ||
            !Number.isSafeInteger(input.revision) || input.revision < 1 || !uuid(input.operation_id) ||
            !Number.isSafeInteger(input.issued_at) || !Number.isSafeInteger(input.expires_at) ||
            input.issued_at > Date.now() || input.expires_at < Date.now() ||
            input.expires_at-input.issued_at > 60000 || input.expires_at-input.issued_at < 1000)
          return reply({ok:false,code:'invalid_or_expired_operation'},400);
        const payload=JSON.stringify({device_id:env.DEVICE_ID,action:input.action,operation_id:input.operation_id,revision:input.revision,
          issued_at:input.issued_at,expires_at:input.expires_at,request_id:crypto.randomUUID()});
        const signature=await sign(env.AGENT_SECRET,payload);
        let upstream;
        try { upstream=await env.VPS_API.fetch('http://vps-agent.internal/v1/command',{
          method:'POST',redirect:'manual',signal:AbortSignal.timeout(8000),
          headers:{'content-type':'application/json','x-pg-signature':signature},body:payload}); }
        catch { return reply({ok:false,code:'command_result_unknown'},502); }
        if (!upstream.ok) {
          if (![400,403].includes(upstream.status)) {
            await upstream.body?.cancel().catch(()=>{});
            return reply({ok:false,code:'command_result_unknown'},502);
          }
          const error=await agentJSON(upstream);
          return reply({ok:false,code:commandDenials.has(error?.code)?error.code:'command_result_unknown'},
            commandDenials.has(error?.code)?upstream.status:502);
        }
        const result=await agentJSON(upstream);
        const operation=operationPublic(result?.operation);
        if(result.ok!==true || operation.operation_id!==input.operation_id || operation.action!==input.action)
          throw new Error('invalid_agent_response');
        return reply({ok:true,operation});
      }
      if (url.pathname === '/v1/status') {
        if (!input || typeof input !== 'object' || !env.VPS_API)
          return reply({ ok: false, code: 'vpc_not_configured' }, 503);
        const payload = JSON.stringify({device_id:env.DEVICE_ID,issued_at:Date.now(),request_id:crypto.randomUUID(),include_analysis:false});
        const signature = await sign(env.AGENT_SECRET,payload);
        let upstream;
        try {
          upstream = await env.VPS_API.fetch('http://vps-agent.internal/v1/status',{
            method:'POST',redirect:'manual',signal:AbortSignal.timeout(8000),
            headers:{'content-type':'application/json','x-pg-signature':signature},body:payload
          });
        } catch { return reply({ok:false,code:'vpc_unavailable'},502); }
        if (!upstream.ok) {await upstream.body?.cancel().catch(()=>{}); return reply({ok:false,code:'agent_rejected'},502);}
        return reply(statusPublic(await agentJSON(upstream)));
      }
      if (!input || input.device_id !== env.DEVICE_ID || !Array.isArray(input.rules) ||
          input.rules.length > 32 ||
          typeof input.policy_enabled !== 'boolean' ||
          (input.default_deny !== undefined && typeof input.default_deny !== 'boolean') ||
          (input.auto_discover !== undefined && typeof input.auto_discover !== 'boolean') ||
          (input.address_families !== undefined && (!Array.isArray(input.address_families) || input.address_families.length < 1 || input.address_families.length > 2 || input.address_families.some(v=>v!==4 && v!==6) || new Set(input.address_families).size!==input.address_families.length)) ||
          !Number.isSafeInteger(input.revision) || input.revision < 1 ||
          !Number.isInteger(input.ttl) || input.ttl < 120 || input.ttl > 86400)
        return reply({ ok: false, code: 'invalid_request' }, 400);
      if(input.policy_trial!==undefined){
        const trial=input.policy_trial;
        if(!object(trial)||Object.keys(trial).some(k=>!['id','seconds'].includes(k))||!uuid(trial.id)||!Number.isInteger(trial.seconds)||trial.seconds<30||trial.seconds>300)return reply({ok:false,code:'invalid_request'},400);
        const probe=JSON.stringify({device_id:env.DEVICE_ID,issued_at:Date.now(),request_id:crypto.randomUUID(),include_analysis:false});let response;
        try{response=await env.VPS_API.fetch('http://vps-agent.internal/v1/status',{method:'POST',redirect:'manual',signal:AbortSignal.timeout(8000),headers:{'content-type':'application/json','x-pg-signature':await sign(env.AGENT_SECRET,probe)},body:probe});}
        catch{return reply({ok:false,code:'vpc_unavailable'},502);}
        if(!response.ok){await response.body?.cancel().catch(()=>{});return reply({ok:false,code:'policy_confirmation_unavailable'},501);}
        const remote=await agentJSON(response);
        if(remote?.ingress?.policy_confirmation!==true)return reply({ok:false,code:'policy_confirmation_unavailable'},501);
      }
      // An observation followed by a sync must traverse the same direct egress.
      if (input.observed_ip !== observed)
        return reply({ ok: false, code: 'source_changed' }, 409);
      if (!env.VPS_API || typeof env.VPS_API.fetch !== 'function')
        return reply({ ok: false, code: 'vpc_not_configured' }, 503);
      const payload = JSON.stringify({
        device_id: env.DEVICE_ID, observed_ip: observed, rules: input.rules,
        policy_enabled: input.policy_enabled, mode:input.mode ?? "standard", ssh:input.ssh ?? {}, default_deny: false,
        auto_discover: false, address_families: input.address_families ?? [4,6], revision: input.revision, ttl: input.ttl,
        issued_at: Date.now(), request_id: crypto.randomUUID(),...(input.policy_trial?{policy_trial:input.policy_trial}:{})
      });
      const signature = await sign(env.AGENT_SECRET, payload);
      let upstream;
      try {
        upstream = await env.VPS_API.fetch('http://vps-agent.internal/v1/sync', {
          method: 'POST', redirect: 'manual', signal: AbortSignal.timeout(8000),
          headers: { 'content-type': 'application/json', 'x-pg-signature': signature },
          body: payload
        });
      } catch { return reply({ ok: false, code: 'vpc_unavailable' }, 502); }
      // Never relay arbitrary internal error pages, addresses or credentials.
      if (!upstream.ok) {await upstream.body?.cancel().catch(()=>{}); return reply({ ok: false, code: 'agent_rejected', agent_status: upstream.status }, 502);}
      const result = await agentJSON(upstream);
      if (result?.ok !== true || result.protocol !== 3 || result.observed_ip !== observed ||
          !Number.isSafeInteger(result.expires_at) || !Number.isSafeInteger(result.applied_at) ||
          result.expires_at < result.applied_at || result.expires_at-result.applied_at > input.ttl || !/^[a-f0-9]{64}$/.test(result.policy_hash || ''))
        throw new Error('invalid_agent_response');
      return reply({ ok:true, protocol:3, policy:policyPublic(result.policy), observed_ip:observed,
        family:observed.includes(':')?6:4, expires_at:result.expires_at, applied_at:result.applied_at, policy_hash:result.policy_hash,...(result.policy_trial?{policy_trial:trialPublic(result.policy_trial)}:{}) });
    } catch (error) {
      if (['invalid_agent_response','response_limit'].includes(error.message))
        return reply({ok:false,code:error.message},502);
      const safe = ['invalid_source_ip', 'body_too_large', 'invalid_request'];
      return reply({ ok: false, code: safe.includes(error.message) ? error.message : 'invalid_request' },
        error.message === 'body_too_large' ? 413 : 400);
    }
  }
};
