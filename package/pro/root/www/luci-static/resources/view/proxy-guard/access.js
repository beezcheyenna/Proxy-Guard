'use strict';
'require view';
'require form';
'require uci';
'require rpc';
'require ui';
'require poll';
'require proxy_guard_pro_i18n as pgI18n';
'require proxy_guard_pro_remote_trial as pgTrial';
const t = pgI18n.gettext;

const configName = 'proxy_guard_access';
function selectedMode(rule){return rule.protection_mode&&rule.protection_mode!=='inherit'?rule.protection_mode:(uci.get(configName,'main','protection_mode')||'standard');}
function effectLabel(rule){
 const mode=selectedMode(rule);
 if(rule.enabled==='0')return t('Disabled');
 if(rule.source_mode==='any'&&mode!=='observe')return t('No protection: bypass enabled');
 return {standard:t('Standard resource protection'),whitelist:t('Whitelist only'),observe:t('Observe only')}[mode]||t('Not available');
}
function sourceLabels(){return {any:t('Bypass all protection (legacy behavior)'),all:t('All sources, resource limits apply'),dynamic:t('Household public IP'),static:t('Static whitelist'),mixed:t('Household IP and static whitelist')};}

const statusCall = rpc.declare({object:'proxy_guard_access',method:'status',expect:{'':{}},reject:true,nobatch:true});
const applyCall = rpc.declare({object:'proxy_guard_access',method:'apply',expect:{'':{}},reject:true});
const actionCalls={preflight:rpc.declare({object:'proxy_guard_access',method:'preflight',expect:{'':{}},reject:true}),restart_xray:rpc.declare({object:'proxy_guard_access',method:'restart_xray',expect:{'':{}},reject:true}),reboot_vps:rpc.declare({object:'proxy_guard_access',method:'reboot_vps',expect:{'':{}},reject:true})};
const errors = {
    policy_trial_storage_invalid:t('Policy confirmation data could not be read. Review saved settings and VPS state.'),
    apply_busy:t('Another settings update is in progress; retry shortly.'),
    session_permissions_updated:t('Sign out of LuCI and sign in again to use updated permissions.'),
    policy_trial_busy:t('Another VPS policy change is awaiting confirmation.'),
    policy_confirmation_unavailable:t('Update the VPS Agent and Worker to use policy confirmation.'),
    agent_protocol_mismatch:t('Update the VPS Agent and control service to the matching protocol version.'),
    policy_not_confirmed:t('The VPS did not confirm the requested inbound policy and address families.'),
    policy_too_large:t('Reduce the number of rules or whitelist addresses.'),
    invalid_endpoint:t('Enter a control-service HTTPS root URL without a path or credentials.'),
    invalid_device_id:t('Enter a valid device ID.'),
    invalid_device_token:t('Enter the paired device secret.'),
    direct_confirmation_required:t('Confirm that the synchronization domain uses a direct connection.'),
    lease_too_short:t('The lease must be at least twice the synchronization interval.'),
    invalid_rule_mode:t('Choose a supported protection mode for this port rule.'),
    whitelist_requires_authorized_sources:t('Whitelist mode requires household or static authorized sources.'),
    source_modes_unavailable:t('Update the VPS Agent and Cloudflare Worker before using the new source options.'),
    per_rule_modes_unavailable:t('Per-port modes are not supported by the connected service. Update the VPS Agent and, if used, the Cloudflare Worker before applying.'),
    invalid_ports:t('Enter ports from 1 to 65535, or a port range.'),
    overlapping_ports:t('Port ranges must not overlap.'),
    overlapping_rules:t('Enabled service rules must not overlap on the same protocol.'),
    invalid_sources:t('Enter valid IPv4 or IPv6 addresses or CIDR networks.'),
    empty_static_whitelist:t('Add at least one address to an enabled static whitelist.'),
    https_failed:t('Synchronization failed; check the direct connection, device secret and control service.'),
    proxy_egress_detected:t('The control service observed the proxy exit. Configure a direct connection before synchronizing.'),
    invalid_worker_response:t('The control service did not confirm this update.'),
    configuration_changed:t('Settings changed during synchronization; waiting for the next update.'),
    operation_busy:t('A maintenance operation is already pending.'),
    remote_operation_denied:t('The Agent denied this action; check its local permissions and credentials.'),
    ssh_timeout_too_short:t('The SSH rescue timeout must allow two heartbeat intervals plus the request timeout.'),
    operation_cooldown:t('Wait briefly before starting another maintenance operation.'),
    ssh_port_overlaps_service:t('The SSH port must not overlap a managed proxy service.'),
    maintenance_not_allowed:t('Enable the matching action locally and on the VPS Agent first.'),
    ssh_requires_independent_path:t('SSH rescue requires an independent HTTPS heartbeat through the proxy.'),
    invalid_path_token:t('Enter the secret for the independent proxy heartbeat.'),
    local_protection_not_ready:t('Local protection could not be prepared; the remote action was not sent.'),
    recovery_not_verified:t('Recovery was not verified before the timeout.'),
    command_result_unknown:t('The request result is unknown; checking operation status without repeating it.')
};
function message(code) { return errors[code] || (code ? t('Check the access settings and connection.') : ''); }
function timeText(value) { return value ? new Date(value*1000).toLocaleString() : t('Not available'); }
return view.extend({
    load:function() { return uci.load(configName); },
    refresh:function() {
        if (this.statusUpdatedAt != null && performance.now()-this.statusUpdatedAt>10000) {
            this.status.className='alert-message warning';
            this.status.replaceChildren(E('strong',{},[t('Synchronization updates are delayed; protection cannot be confirmed.')]));
            for (const button of Object.values(this.actionButtons||{})) button.disabled=true;
        }
        if (this.statusRequest) return this.statusRequest;
        this.statusRequest=statusCall().then(s=>{

            const names={disabled:t('Synchronization is off'),waiting:t('Waiting to synchronize'),stopped:t('Synchronization stopped'),
                syncing:t('Synchronizing with the VPS'),restoring:t('Restore previous VPS policy')+'…',confirming:t('VPS policy is waiting for confirmation'),synced:t('VPS confirmed the update'),error:t('Synchronization needs attention')};
            if (!s || s.ok === false || !Object.prototype.hasOwnProperty.call(names,s.phase)) throw new Error('invalid_status');
            this.status.className='alert-message '+(s.phase==='error'||s.phase==='restoring'||s.phase==='confirming'||s.last_known||s.stale||s.remote_health&&s.remote_health.ok===false?'warning':'notice');
            const lines=[E('strong',{},[names[s.phase]||t('Waiting to synchronize')])];
            for(const family of ['4','6']) {
                const a=s.addresses&&s.addresses[family];
                if(a) lines.push(E('p',{},['IPv'+family+': '+a.ip+' · '+t('Lease expires')+': '+timeText(a.expires_at)]));
            }
            if(s.policy_trial&&s.policy_trial.last_result&&s.policy_trial.last_result.phase==='rolled_back')lines.push(E('p',{},[t('The previous VPS policy was restored after an unconfirmed change.')]));
            if(s.attempted_at) lines.push(E('p',{},[t('Last attempt')+': '+timeText(s.attempted_at)]));
            if(s.error) lines.push(E('p',{},[message(s.error)]));
            if(s.stale) lines.push(E('p',{},[t('The synchronization process is not updating its status.')]));
            const remote=s.remote_health;
            if(s.last_known)lines.push(E('p',{class:'alert-message warning'},[t('Synchronization is off. The following VPS policy is last known state, not a current confirmation. Rules may remain active and dynamic authorizations expire.')]));
            if(remote&&!s.last_known) {
                const health=(remote.remote||{}).health||{};
                lines.push(E('p',{},[t('VPS access readiness')+': '+(remote.ok?t('Ready'):t('Unavailable'))]));
                for(const item of [['service_ok',t('VPS services')],['revision_ok',t('Policy revision confirmed')],['authorization_ok',t('Selected address families authorized')]]) {
                    if(remote[item[0]]!=null) lines.push(E('p',{},[item[1]+': '+(remote[item[0]]?t('Ready'):t('Unavailable'))]));
                }
                for(const service of health.services||[]) lines.push(E('p',{},[service.name+': '+(service.ok?t('Running'):t('Not running'))]));
            }
            const agent=(remote||{}).remote||{};
            if(agent.ingress) lines.push(E('p',{},[t('VPS inbound policy')+': '+(agent.ingress.enabled===false?t('VPS access rules are off'):agent.ingress.enabled!==true?t('Not available'):agent.ingress.default_deny===false&&agent.ingress.auto_discover===false?t('Restrict listed ports only'):t('VPS policy does not match selected-port protection; update the Agent.'))]));
            if(agent.inventory) {
                lines.push(E('p',{},[t('Discovered listeners')+': '+agent.inventory.count]));
                for(const row of agent.inventory.listeners||[]) lines.push(E('p',{},[row.protocol.toUpperCase()+' '+row.port+' · IPv'+row.family+' · '+(row.processes||[]).map(p=>p.name).join(', ')]));
                if(agent.inventory.truncated) lines.push(E('p',{},[t('The listener list is truncated. Discovery does not change access rules.')]));
            }
            const modes={whitelist:t('Whitelist only'),standard:t('Standard resource protection'),observe:t('Observe only')};
            const bypass=Object.entries(agent.ingress&&agent.ingress.rule_effects||{}).filter(([,effect])=>effect==='bypass').map(([id])=>id);
            if(bypass.length)lines.push(E('p',{class:'alert-message warning'},[t('VPS confirmed protection bypass for: ')+bypass.join(', ')]));
            if(agent.ingress) lines.push(E('p',{},[t('Default port protection mode')+': '+(modes[agent.ingress.mode]||t('Not available'))]));
            if(s.path_health) lines.push(E('p',{},[t('Independent proxy heartbeat')+': '+(s.path_health.ok?t('Ready'):t('Unavailable'))]));
            const readinessReasons={both_heartbeats_required:t('Waiting for both authenticated heartbeats'),management_confirmation_required:t('Confirm the SSH management session in settings'),fresh_household_authorization_required:t('Waiting for a fresh household IP authorization'),ssh_listener_not_verified:t('The selected SSH port is not owned by a verified SSH service'),authorized_ssh_session_required:t('Connect by SSH from an authorized management address, then check again')};
            const rescue=agent.ssh_rescue;
            if(rescue&&rescue.managed) {
                lines.push(E('p',{},[t('SSH management')+': '+(rescue.emergency?t('Emergency access active'):rescue.armed?t('Management protection active'):t('Waiting for management verification'))]));
                if(rescue.emergency) {
                    const unlimited=rescue.public_unlimited===true||agent.ingress&&agent.ingress.ssh&&agent.ingress.ssh.open_seconds===0;
                    const window=rescue.effective_scope!=='public'?'':unlimited?t('Open until household authorization is restored'):t('Public access remaining (seconds)')+': '+rescue.public_remaining;
                    lines.push(E('p',{},[t('Emergency source scope')+': '+(rescue.effective_scope==='public'?t('Public Internet'):t('Management addresses and last household IP'))+(window?' · '+window:'')]));
                }
                lines.push(E('p',{},[t('Control heartbeat age (seconds)')+': '+(rescue.control_age==null?t('Not available'):rescue.control_age)+' · '+t('Proxy heartbeat age (seconds)')+': '+(rescue.proxy_age==null?t('Not available'):rescue.proxy_age)]));
                if(rescue.preflight&&!rescue.preflight.ok) lines.push(E('p',{},[t('Management check')+': '+(readinessReasons[rescue.preflight.reason]||t('Needs attention'))]));
            }
            const resourceReasons={temporary_connection_limit:t('New connections temporarily limited'),concurrency_threshold:t('Concurrent connection threshold exceeded'),connection_rate_threshold:t('New connection rate exceeded'),fallback_bandwidth:t('Verified fallback bandwidth threshold exceeded')};
            for(const event of ((agent.events||{}).events||[]).filter(e=>e.kind==='resource_anomaly').slice(-8)) {
                const e=event.evidence||{};lines.push(E('p',{},[timeText(event.time)+' · '+(e.source_ip||'')+' · '+(e.port||'')+' · '+(resourceReasons[e.reason]||t('Resource threshold exceeded'))]));
            }
            const resources=agent.resources||{};
            if(resources.native_checks) lines.push(E('p',{},[t('REALITY configuration check')+': '+(resources.native_checks.configured?(resources.native_checks.ok?t('Ready'):t('Needs attention')):t('Not configured'))]));
            if(resources.bandwidth_requested&&resources.fallback_telemetry_available===false) lines.push(E('p',{},[t('Fallback bandwidth monitoring needs a trusted data source configured on the VPS Agent.')]));
            for(const item of (resources.sources||[]).slice(0,12)) lines.push(E('p',{},[item.source_ip+' · '+item.service+' / '+item.protocol.toUpperCase()+' '+(item.port||'')+' · '+t('Bytes observed')+': '+item.bytes]));
            if(agent.maintenance&&agent.maintenance.state_error) lines.push(E('p',{},[t('Maintenance record storage needs attention; restart actions are disabled.')]));
            const job=s.operation;
            const phases={queued:t('Queued'),accepted:t('Request accepted'),dispatching:t('Restarting'),verifying:t('Verifying recovery'),complete:t('Recovery verified'),failed:t('Operation failed'),uncertain:t('Result unknown'),indeterminate:t('Interrupted; not repeated automatically')};
            if(job) lines.push(E('p',{},[t('Maintenance operation')+': '+(phases[job.phase]||job.phase)+(job.error?' · '+message(job.error):'')]));
            const pending=job&&!['complete','failed','indeterminate'].includes(job.phase);
            for(const [action,button]of Object.entries(this.actionButtons||{})) button.disabled=!!(this.busy||pending||s.enabled!==true||action!=='preflight'&&!(s.permissions||{})[action]);
            this.status.replaceChildren(...lines);
            this.statusUpdatedAt=performance.now();
        }).catch(()=>{
            this.status.className='alert-message warning';
            this.status.replaceChildren(E('strong',{},[t('Cannot read synchronization status; retrying automatically.')]));
            for (const button of Object.values(this.actionButtons||{})) button.disabled=true;
        }).finally(()=>{this.statusRequest=null;});
        return this.statusRequest;
    },
    render:function() {
        const m=this.map=new form.Map(configName,null,
            t('Synchronize your household public IP and inspect VPS service health through direct HTTPS or Cloudflare. Proxy traffic connects directly to the VPS.'));
        let s=m.section(form.NamedSection,'main','access',t('Connection settings'));
        s.addremove=false;
        let o=s.option(form.Flag,'enabled',t('Synchronize with the VPS'),
            t('Changes take effect after Save & Apply. Stopping synchronization does not remove VPS rules. Dynamic authorizations expire; configured resource limits and SSH rescue remain in effect.'));
        o.rmempty=false;
        o=s.option(form.ListValue,'transport',t('Control channel'));
        o.value('cloudflare',t('Cloudflare Worker and Tunnel'));
        o.value('direct',t('Direct HTTPS to Agent'));
        o.default='cloudflare';
        o=s.option(form.Flag,'health_guard',t('Require VPS service health before restoring access'),
            t('A missing or failed remote health report withholds the local access permit. Local proxy checks remain required.'));
        o.rmempty=false;
        o=s.option(form.Value,'health_interval',t('VPS health check interval (seconds)'));o.default='10';o.datatype='range(5,60)';o.rmempty=false;
        o=s.option(form.Value,'endpoint',t('Control service HTTPS address'));o.placeholder='https://your-worker.example';o.rmempty=false;o.depends('enabled','1');o.retain=true;
        o=s.option(form.Value,'device_id',t('Device ID'));o.default='home';o.rmempty=false;o.depends('enabled','1');o.retain=true;
        o=s.option(form.Value,'device_token',t('Device secret'),t('Leave empty to keep the paired device secret.'));o.password=true;o.rmempty=true;
        o.cfgvalue=function(){return '';};o.depends('enabled','1');o.retain=true;
        o=s.option(form.Flag,'direct_confirmed',t('I have confirmed the control service uses a direct connection'),
            t('The control request must bypass the proxy. Configure direct routing before enabling synchronization. A detected proxy exit is rejected.'));
        o.rmempty=false;
        o=s.option(form.ListValue,'family',t('Address families'),t('Choose the public address families to authorize dynamically. Removing a family revokes its dynamic lease after the VPS confirms the update; static rules remain independent.'));
        o.value('ipv4',t('IPv4'));o.value('ipv6',t('IPv6'));o.value('both',t('IPv4 and IPv6'));o.default='ipv4';
        for(const item of [['interval',t('Synchronization interval (seconds)'),300,60,3600],
            ['ttl',t('Dynamic lease duration (seconds)'),900,120,86400],['timeout',t('Control request timeout (seconds)'),8,2,15]]) {
            o=s.option(form.Value,item[0],item[1]);o.default=String(item[2]);o.datatype='range('+item[3]+','+item[4]+')';o.rmempty=false;
        }
        s=m.section(form.NamedSection,'main','access',t('VPS service rules'),
            t('Only selected service ports are managed. Other ports keep the existing system firewall policy. SSH management is separate and disabled by default.')+' '+t('Only add ports you intend to filter. Selecting a panel, API, or subscription port filters that service too. Services sharing the same IP, protocol, and port cannot be separated by URL path or SNI here. SSH has separate settings.'));
        o=s.option(form.Flag,'policy_enabled',t('Enable VPS access rules'));
        o.default='1';o.rmempty=false;
        o=s.option(form.Flag,'policy_confirm',t('Confirm VPS policy changes before keeping them'));
        o.default='1';o.rmempty=false;o.description=t('Recommended. The VPS restores its previous selected-port policy if a changed policy is not confirmed. Disabling this applies changes immediately.');
        o=s.option(form.Value,'policy_confirm_seconds',t('VPS confirmation window (seconds)'));o.default='60';o.datatype='range(30,300)';o.rmempty=false;o.depends('policy_confirm','1');
        o=s.option(form.ListValue,'protection_mode',t('Default port protection mode'));
        o.value('standard',t('Standard resource protection'));o.value('whitelist',t('Whitelist only'));o.value('observe',t('Observe only'));o.default='standard';o.rmempty=false;
        s=m.section(form.GridSection,'rule',t('Services'),
            t('Discovery lists candidate ports only. Whitelist mode requires an authorized source; standard mode applies resource limits; observe mode records without blocking. Unrestricted rules keep the original system firewall behavior.')+' '+t('Each rule has its own mode, sources, thresholds and timers. Ports grouped in one rule share these settings. Create separate rules for different settings.'));
        s.addremove=true;s.anonymous=false;s.sortable=false;s.nodescriptions=true;
        o=s.option(form.Flag,'enabled',t('Enabled'));o.default='1';o.rmempty=false;
        o=s.option(form.Value,'name',t('Service name'));o.rmempty=false;o.datatype='maxlength(64)';
        o=s.option(form.ListValue,'protocol',t('Protocol'));o.value('tcp','TCP');o.value('udp','UDP');o.value('both','TCP + UDP');o.default='tcp';o.textvalue=function(section){return {tcp:'TCP',udp:'UDP',both:'TCP + UDP'}[this.cfgvalue(section)||'tcp'];};
        o=s.option(form.ListValue,'protection_mode',t('Port protection mode'));
        o.value('inherit',t('Use default mode'));o.value('whitelist',t('Whitelist only'));o.value('standard',t('Standard resource protection'));o.value('observe',t('Observe only'));o.default='inherit';o.rmempty=false;
        o.textvalue=function(section){return effectLabel(uci.get(configName,section)||{});};
        o=s.option(form.DynamicList,'ports',t('Ports'));o.placeholder='443';o.rmempty=false;
        o.validate=function(section,value) {
            const ports=Array.isArray(value)?value:[value];
            return ports.length&&ports.every(p=>{
                const match=/^([1-9][0-9]{0,4})(?:-([1-9][0-9]{0,4}))?$/.exec(p||'');
                return match&&Number(match[1])<=Number(match[2]||match[1])&&Number(match[2]||match[1])<=65535;
            })||t('Enter ports from 1 to 65535, or a port range.');
        };
        o=s.option(form.ListValue,'source_mode',t('Allowed or exempt sources'),t('All sources keeps standard resource limits active. Household and static addresses are allowed in whitelist mode and exempt from standard limits. Legacy bypass disables this rule protection.'));
        o.value('all',t('All sources, resource limits apply'));o.value('any',t('Bypass all protection (legacy behavior)'));o.value('dynamic',t('Household public IP'));
        o.value('static',t('Static whitelist'));o.value('mixed',t('Household IP and static whitelist'));o.default='dynamic';o.textvalue=function(section){return sourceLabels()[this.cfgvalue(section)||'dynamic'];};
        o=s.option(form.DynamicList,'sources',t('Static IP addresses or networks'));
        o.datatype='ipaddr';o.depends('source_mode','static');o.depends('source_mode','mixed');o.retain=true;
        for(const item of [['rate_enabled',t('Limit new connection rate'),true],['connections_enabled',t('Limit concurrent connections'),true],['bandwidth_enabled',t('Limit verified fallback bandwidth'),false]]) {
            o=s.option(form.Flag,item[0],item[1]);o.default=item[2]?'1':'0';o.rmempty=false;o.modalonly=true;
        }
        for(const item of [['rate',t('New connections per second'),40,1,10000],['burst',t('Connection burst allowance'),80,1,20000],['connections',t('Concurrent connection limit'),128,1,10000],['bandwidth',t('Fallback bandwidth per direction (bytes per second)'),1048576,1024,1073741824],['sustain',t('Bandwidth threshold duration (seconds)'),10,1,300],['cooldown',t('New connection cooldown (seconds)'),30,1,3600],['window',t('Observation window (seconds)'),60,5,600]]) {
            o=s.option(form.Value,item[0],item[1]);o.default=String(item[2]);o.datatype='range('+item[3]+','+item[4]+')';o.rmempty=false;o.modalonly=true;
        }
        s=m.section(form.NamedSection,'main','access',t('Independent proxy heartbeat'),t('Use an Agent HTTPS endpoint reached through the local SOCKS proxy, separately from the control channel.'));
        o=s.option(form.Flag,'path_watch',t('Enable proxy-path heartbeat'));o.rmempty=false;
        o=s.option(form.Value,'path_endpoint',t('Agent HTTPS address through the proxy'));o.depends('path_watch','1');o.retain=true;
        o=s.option(form.Value,'path_token',t('Proxy heartbeat secret'),t('Leave empty to keep the paired secret.'));o.password=true;o.cfgvalue=()=>'';o.depends('path_watch','1');o.retain=true;
        o=s.option(form.Value,'path_interval',t('Proxy heartbeat interval (seconds)'));o.default='10';o.datatype='range(5,60)';o.rmempty=false;o.depends('path_watch','1');
        s=m.section(form.NamedSection,'main','access',t('SSH management'),t('SSH authentication settings remain unchanged. Access is managed only after both heartbeats and an authorized SSH session are verified.'));
        o=s.option(form.Flag,'ssh_managed',t('Manage SSH access'));o.rmempty=false;
        o=s.option(form.Value,'ssh_port',t('SSH port'));o.default='22';o.datatype='port';o.rmempty=false;o.depends('ssh_managed','1');
        o=s.option(form.DynamicList,'ssh_managers',t('Management IP addresses or networks'));o.datatype='ipaddr';o.depends('ssh_managed','1');o.retain=true;
        o=s.option(form.Flag,'ssh_confirmed',t('I have verified an authorized SSH management session'));o.rmempty=false;o.depends('ssh_managed','1');
        o=s.option(form.Flag,'ssh_rescue',t('Enable emergency SSH access'));o.default='1';o.rmempty=false;o.depends('ssh_managed','1');
        o=s.option(form.Value,'ssh_after',t('Both heartbeats lost for (seconds)'));o.default='60';o.datatype='range(10,3600)';o.rmempty=false;o.depends({ssh_managed:'1',ssh_rescue:'1'});
        o=s.option(form.ListValue,'ssh_scope',t('Emergency source scope'));o.value('public',t('Public Internet'));o.value('restricted',t('Management addresses and last household IP'));o.default='public';o.rmempty=false;o.depends({ssh_managed:'1',ssh_rescue:'1'});
        o=s.option(form.Value,'ssh_open_seconds',t('Public emergency window (seconds)'));
        o.default='0';o.datatype='uinteger';o.rmempty=false;o.depends({ssh_managed:'1',ssh_rescue:'1',ssh_scope:'public'});
        o.validate=(section,value)=>/^\d+$/.test(value||'')&&(Number(value)===0||Number(value)>=30&&Number(value)<=3600)||t('Enter 0 to keep rescue open, or an integer from 30 to 3600 seconds.');
        o.description=t('0 keeps emergency SSH open until household authorization is restored. Use 30 to 3600 for a timed window.')+' '+t('Warning: a timed window closes public access when it expires. If your IP has changed and no allowed management source is reachable, you may lose SSH access. An unlimited window keeps SSH publicly reachable during the outage; SSH authentication and the system firewall still apply.');
        s=m.section(form.NamedSection,'main','access',t('Remote maintenance'),t('The VPS Agent must also explicitly allow each action. A request being accepted does not mean recovery is complete.'));
        o=s.option(form.Flag,'allow_restart',t('Allow restarting the proxy core'));o.rmempty=false;
        o=s.option(form.Flag,'allow_reboot',t('Allow rebooting the VPS'));o.rmempty=false;
        o=s.option(form.Value,'maintenance_timeout',t('Recovery verification timeout (seconds)'));o.default='180';o.datatype='range(30,600)';o.rmempty=false;
        this.statusUpdatedAt=performance.now();
        this.status=E('div',{id:'pg-access-status',class:'alert-message notice',role:'status','aria-live':'polite'},[t('Waiting to synchronize')]);
        return m.render().then(node=>{
            this.refresh();poll.add(()=>this.refresh(),5);setTimeout(()=>pgTrial.attach(this),0);
            this.actionButtons={};
            const actions=E('div',{class:'cbi-page-actions'},[]);
            for(const [action,label]of [['preflight',t('Check management readiness')],['restart_xray',t('Restart proxy core')],['reboot_vps',t('Reboot VPS')]]) {
                const button=E('button',{class:'cbi-button '+(action==='preflight'?'cbi-button-neutral':'cbi-button-action'),type:'button',disabled:true,click:()=>this.confirmAction(action,label)},[label]);
                this.actionButtons[action]=button;actions.appendChild(button);
            }
            actions.appendChild(E('button',{class:'cbi-button cbi-button-neutral',type:'button',click:()=>this.preparePolicyRelease()},[t('Prepare to remove VPS rules')]));
            const preview=E('button',{class:'cbi-button cbi-button-neutral',type:'button',click:()=>this.previewRules()},[t('Preview service rules')]);actions.appendChild(preview);actions.appendChild(E('a',{class:'cbi-button',href:'proxy-guard-access-raw'},[t('Raw UCI configuration')]));
            return pgI18n.decorate(E('div',{},[E('h2',{},[t('VPS access rules')]),this.status,node,actions]));
        });
    },
    reloadAccessConfig:function(){uci.unload(configName);return this.map.load().then(()=>this.map.reset()).then(()=>ui.changes.init());},
    preparePolicyRelease:function(){
        pgI18n.modal(ui,t('Remove VPS rules'),[E('p',{},[t('Prepare to turn off this plugin VPS port rules and SSH management while synchronization remains enabled. Save & Apply, then confirm the VPS change. After the VPS confirms removal you may stop synchronization. The system firewall remains in effect.')]),E('div',{class:'right'},[
            E('button',{type:'button',class:'cbi-button',click:ui.hideModal},[t('Cancel')]),
            E('button',{type:'button',class:'cbi-button cbi-button-action',click:()=>{ui.hideModal();return this.map.parse().then(()=>{uci.set(configName,'main','enabled','1');uci.set(configName,'main','policy_enabled','0');uci.set(configName,'main','ssh_managed','0');return this.map.load();}).then(()=>this.map.reset()).then(()=>ui.showIndicator('pg-access-draft',t('Unsaved changes'))).catch(e=>ui.addNotification(null,E('p',{},[e.message]),'error'));}},[t('Prepare changes')])])]);
    },
    confirmAction:function(action,label) {
        if(action==='preflight') return this.sendAction(action);
        pgI18n.modal(ui,label,[E('p',{},[t('This interrupts proxy access. Local protection is prepared before the request is sent.')]),E('div',{class:'right'},[
            E('button',{class:'cbi-button',click:ui.hideModal},[t('Cancel')]),
            E('button',{class:'cbi-button cbi-button-negative',click:()=>{ui.hideModal();this.sendAction(action);}},[t('Confirm')])])]);
    },
    sendAction:function(action) {
        if(this.busy)return Promise.resolve();this.busy=true;
        return actionCalls[action]().then(result=>{
            if(!result.ok)throw new Error(message(result.error));
            return this.refresh();
        }).catch(error=>ui.addNotification(null,E('p',{},[error.message||t('Operation failed')]),'error')).finally(()=>{this.busy=false;this.refresh();});
    },
    previewRules:function() {
        return this.map.parse().then(()=>{
            const rows=[E('tr',{},[t('Service name'),t('Protocol'),t('Ports'),t('Port protection mode'),t('IP filtering'),t('Static IP addresses or networks')].map(label=>E('th',{},[label])))];
            const sourceModes=sourceLabels();
            uci.sections(configName,'rule',rule=>{if(rule.enabled!=='0') rows.push(E('tr',{},[
                E('td',{},[rule.name||rule['.name']]),E('td',{},[(rule.protocol||'tcp').toUpperCase()]),
                E('td',{},[(Array.isArray(rule.ports)?rule.ports:[rule.ports||'']).join(', ')]),
                E('td',{},[effectLabel(rule)]),
                E('td',{},[sourceModes[rule.source_mode||'dynamic']]),E('td',{},[(Array.isArray(rule.sources)?rule.sources:[]).join(', ')])]));});
            pgI18n.modal(ui,t('Service rule preview'),[E('p',{},[t('This preview has not been applied. Unselected ports keep the existing system firewall policy.')]),
                E('table',{class:'table'},rows),E('div',{class:'right'},[E('button',{class:'cbi-button',click:ui.hideModal},[t('Close')])])]);
        }).catch(error=>ui.addNotification(null,E('p',{},[error.message]),'error'));
    },
    handleSave:function(){return this.map.save().then(()=>{ui.hideIndicator('pg-access-draft');return ui.changes.init();});},
    handleReset:function(){ui.hideIndicator('pg-access-draft');return this.map.reset();},
    handleSaveApply:function(){
        return this.map.save().then(()=>applyCall()).then(result=>{
            if(!result.ok) throw new Error(message(result.error));
            ui.hideIndicator('pg-access-draft');pgTrial.begin(result.policy_trial);
            return Promise.all([this.refresh(),ui.changes.init()]);
        }).catch(error=>ui.addNotification(null,E('p',{},[error.message||t('Apply failed')]),'error'));
    }
});
