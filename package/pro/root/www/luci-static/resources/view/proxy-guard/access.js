'use strict';
'require view';
'require form';
'require uci';
'require rpc';
'require ui';
'require poll';
'require proxy_guard_i18n as pgI18n';
'require proxy_guard_remote_trial as pgTrial';

const configName = 'proxy_guard_access';
function selectedMode(rule){return rule.protection_mode&&rule.protection_mode!=='inherit'?rule.protection_mode:(uci.get(configName,'main','protection_mode')||'standard');}
function effectLabel(rule){
 const mode=selectedMode(rule);
 if(rule.enabled==='0')return _('Disabled');
 if(rule.source_mode==='any'&&mode!=='observe')return _('No protection: bypass enabled');
 return {standard:_('Standard resource protection'),whitelist:_('Whitelist only'),observe:_('Observe only')}[mode]||_('Not available');
}
function sourceLabels(){return {any:_('Bypass all protection (legacy behavior)'),all:_('All sources, resource limits apply'),dynamic:_('Household public IP'),static:_('Static whitelist'),mixed:_('Household IP and static whitelist')};}

const statusCall = rpc.declare({object:'proxy_guard_access',method:'status',expect:{'':{}},reject:true,nobatch:true});
const applyCall = rpc.declare({object:'proxy_guard_access',method:'apply',expect:{'':{}},reject:true});
const actionCalls={preflight:rpc.declare({object:'proxy_guard_access',method:'preflight',expect:{'':{}},reject:true}),restart_xray:rpc.declare({object:'proxy_guard_access',method:'restart_xray',expect:{'':{}},reject:true}),reboot_vps:rpc.declare({object:'proxy_guard_access',method:'reboot_vps',expect:{'':{}},reject:true})};
const errors = {
    policy_trial_storage_invalid:_('Policy confirmation data could not be read. Review saved settings and VPS state.'),
    apply_busy:_('Another settings update is in progress; retry shortly.'),
    session_permissions_updated:_('Sign out of LuCI and sign in again to use updated permissions.'),
    policy_trial_busy:_('Another VPS policy change is awaiting confirmation.'),
    policy_confirmation_unavailable:_('Update the VPS Agent and Worker to use policy confirmation.'),
    agent_protocol_mismatch:_('Update the VPS Agent and control service to the matching protocol version.'),
    policy_not_confirmed:_('The VPS did not confirm the requested inbound policy and address families.'),
    policy_too_large:_('Reduce the number of rules or whitelist addresses.'),
    invalid_endpoint:_('Enter a control-service HTTPS root URL without a path or credentials.'),
    invalid_device_id:_('Enter a valid device ID.'),
    invalid_device_token:_('Enter the paired device secret.'),
    direct_confirmation_required:_('Confirm that the synchronization domain uses a direct connection.'),
    lease_too_short:_('The lease must be at least twice the synchronization interval.'),
    invalid_rule_mode:_('Choose a supported protection mode for this port rule.'),
    whitelist_requires_authorized_sources:_('Whitelist mode requires household or static authorized sources.'),
    source_modes_unavailable:_('Update the VPS Agent and Cloudflare Worker before using the new source options.'),
    per_rule_modes_unavailable:_('Per-port modes are not supported by the connected service. Update the VPS Agent and, if used, the Cloudflare Worker before applying.'),
    invalid_ports:_('Enter ports from 1 to 65535, or a port range.'),
    overlapping_ports:_('Port ranges must not overlap.'),
    overlapping_rules:_('Enabled service rules must not overlap on the same protocol.'),
    invalid_sources:_('Enter valid IPv4 or IPv6 addresses or CIDR networks.'),
    empty_static_whitelist:_('Add at least one address to an enabled static whitelist.'),
    https_failed:_('Synchronization failed; check the direct connection, device secret and control service.'),
    proxy_egress_detected:_('The control service observed the proxy exit. Configure a direct connection before synchronizing.'),
    invalid_worker_response:_('The control service did not confirm this update.'),
    configuration_changed:_('Settings changed during synchronization; waiting for the next update.'),
    operation_busy:_('A maintenance operation is already pending.'),
    remote_operation_denied:_('The Agent denied this action; check its local permissions and credentials.'),
    ssh_timeout_too_short:_('The SSH rescue timeout must allow two heartbeat intervals plus the request timeout.'),
    operation_cooldown:_('Wait briefly before starting another maintenance operation.'),
    ssh_port_overlaps_service:_('The SSH port must not overlap a managed proxy service.'),
    maintenance_not_allowed:_('Enable the matching action locally and on the VPS Agent first.'),
    ssh_requires_independent_path:_('SSH rescue requires an independent HTTPS heartbeat through the proxy.'),
    invalid_path_token:_('Enter the secret for the independent proxy heartbeat.'),
    local_protection_not_ready:_('Local protection could not be prepared; the remote action was not sent.'),
    recovery_not_verified:_('Recovery was not verified before the timeout.'),
    command_result_unknown:_('The request result is unknown; checking operation status without repeating it.')
};
function message(code) { return errors[code] || (code ? _('Check the access settings and connection.') : ''); }
function timeText(value) { return value ? new Date(value*1000).toLocaleString() : _('Not available'); }
return view.extend({
    load:function() { return uci.load(configName); },
    refresh:function() {
        if (this.statusUpdatedAt != null && performance.now()-this.statusUpdatedAt>10000) {
            this.status.className='alert-message warning';
            this.status.replaceChildren(E('strong',{},[_('Synchronization updates are delayed; protection cannot be confirmed.')]));
            for (const button of Object.values(this.actionButtons||{})) button.disabled=true;
        }
        if (this.statusRequest) return this.statusRequest;
        this.statusRequest=statusCall().then(s=>{

            const names={disabled:_('Synchronization is off'),waiting:_('Waiting to synchronize'),stopped:_('Synchronization stopped'),
                syncing:_('Synchronizing with the VPS'),restoring:_('Restore previous VPS policy')+'…',confirming:_('VPS policy is waiting for confirmation'),synced:_('VPS confirmed the update'),error:_('Synchronization needs attention')};
            if (!s || s.ok === false || !Object.prototype.hasOwnProperty.call(names,s.phase)) throw new Error('invalid_status');
            this.status.className='alert-message '+(s.phase==='error'||s.phase==='restoring'||s.phase==='confirming'||s.last_known||s.stale||s.remote_health&&s.remote_health.ok===false?'warning':'notice');
            const lines=[E('strong',{},[names[s.phase]||_('Waiting to synchronize')])];
            for(const family of ['4','6']) {
                const a=s.addresses&&s.addresses[family];
                if(a) lines.push(E('p',{},['IPv'+family+': '+a.ip+' · '+_('Lease expires')+': '+timeText(a.expires_at)]));
            }
            if(s.policy_trial&&s.policy_trial.last_result&&s.policy_trial.last_result.phase==='rolled_back')lines.push(E('p',{},[_('The previous VPS policy was restored after an unconfirmed change.')]));
            if(s.attempted_at) lines.push(E('p',{},[_('Last attempt')+': '+timeText(s.attempted_at)]));
            if(s.error) lines.push(E('p',{},[message(s.error)]));
            if(s.stale) lines.push(E('p',{},[_('The synchronization process is not updating its status.')]));
            const remote=s.remote_health;
            if(s.last_known)lines.push(E('p',{class:'alert-message warning'},[_('Synchronization is off. The following VPS policy is last known state, not a current confirmation. Rules may remain active and dynamic authorizations expire.')]));
            if(remote&&!s.last_known) {
                const health=(remote.remote||{}).health||{};
                lines.push(E('p',{},[_('VPS access readiness')+': '+(remote.ok?_('Ready'):_('Unavailable'))]));
                for(const item of [['service_ok',_('VPS services')],['revision_ok',_('Policy revision confirmed')],['authorization_ok',_('Selected address families authorized')]]) {
                    if(remote[item[0]]!=null) lines.push(E('p',{},[item[1]+': '+(remote[item[0]]?_('Ready'):_('Unavailable'))]));
                }
                for(const service of health.services||[]) lines.push(E('p',{},[service.name+': '+(service.ok?_('Running'):_('Not running'))]));
            }
            const agent=(remote||{}).remote||{};
            if(agent.ingress) lines.push(E('p',{},[_('VPS inbound policy')+': '+(agent.ingress.enabled===false?_('VPS access rules are off'):agent.ingress.enabled!==true?_('Not available'):agent.ingress.default_deny===false&&agent.ingress.auto_discover===false?_('Restrict listed ports only'):_('VPS policy does not match selected-port protection; update the Agent.'))]));
            if(agent.inventory) {
                lines.push(E('p',{},[_('Discovered listeners')+': '+agent.inventory.count]));
                for(const row of agent.inventory.listeners||[]) lines.push(E('p',{},[row.protocol.toUpperCase()+' '+row.port+' · IPv'+row.family+' · '+(row.processes||[]).map(p=>p.name).join(', ')]));
                if(agent.inventory.truncated) lines.push(E('p',{},[_('The listener list is truncated. Discovery does not change access rules.')]));
            }
            const modes={whitelist:_('Whitelist only'),standard:_('Standard resource protection'),observe:_('Observe only')};
            const bypass=Object.entries(agent.ingress&&agent.ingress.rule_effects||{}).filter(([,effect])=>effect==='bypass').map(([id])=>id);
            if(bypass.length)lines.push(E('p',{class:'alert-message warning'},[_('VPS confirmed protection bypass for: ')+bypass.join(', ')]));
            if(agent.ingress) lines.push(E('p',{},[_('Default port protection mode')+': '+(modes[agent.ingress.mode]||_('Not available'))]));
            if(s.path_health) lines.push(E('p',{},[_('Independent proxy heartbeat')+': '+(s.path_health.ok?_('Ready'):_('Unavailable'))]));
            const readinessReasons={both_heartbeats_required:_('Waiting for both authenticated heartbeats'),management_confirmation_required:_('Confirm the SSH management session in settings'),fresh_household_authorization_required:_('Waiting for a fresh household IP authorization'),ssh_listener_not_verified:_('The selected SSH port is not owned by a verified SSH service'),authorized_ssh_session_required:_('Connect by SSH from an authorized management address, then check again')};
            const rescue=agent.ssh_rescue;
            if(rescue&&rescue.managed) {
                lines.push(E('p',{},[_('SSH management')+': '+(rescue.emergency?_('Emergency access active'):rescue.armed?_('Management protection active'):_('Waiting for management verification'))]));
                if(rescue.emergency) {
                    const unlimited=rescue.public_unlimited===true||agent.ingress&&agent.ingress.ssh&&agent.ingress.ssh.open_seconds===0;
                    const window=rescue.effective_scope!=='public'?'':unlimited?_('Open until household authorization is restored'):_('Public access remaining (seconds)')+': '+rescue.public_remaining;
                    lines.push(E('p',{},[_('Emergency source scope')+': '+(rescue.effective_scope==='public'?_('Public Internet'):_('Management addresses and last household IP'))+(window?' · '+window:'')]));
                }
                lines.push(E('p',{},[_('Control heartbeat age (seconds)')+': '+(rescue.control_age==null?_('Not available'):rescue.control_age)+' · '+_('Proxy heartbeat age (seconds)')+': '+(rescue.proxy_age==null?_('Not available'):rescue.proxy_age)]));
                if(rescue.preflight&&!rescue.preflight.ok) lines.push(E('p',{},[_('Management check')+': '+(readinessReasons[rescue.preflight.reason]||_('Needs attention'))]));
            }
            const resourceReasons={temporary_connection_limit:_('New connections temporarily limited'),concurrency_threshold:_('Concurrent connection threshold exceeded'),connection_rate_threshold:_('New connection rate exceeded'),fallback_bandwidth:_('Verified fallback bandwidth threshold exceeded')};
            for(const event of ((agent.events||{}).events||[]).filter(e=>e.kind==='resource_anomaly').slice(-8)) {
                const e=event.evidence||{};lines.push(E('p',{},[timeText(event.time)+' · '+(e.source_ip||'')+' · '+(e.port||'')+' · '+(resourceReasons[e.reason]||_('Resource threshold exceeded'))]));
            }
            const resources=agent.resources||{};
            if(resources.native_checks) lines.push(E('p',{},[_('REALITY configuration check')+': '+(resources.native_checks.configured?(resources.native_checks.ok?_('Ready'):_('Needs attention')):_('Not configured'))]));
            if(resources.bandwidth_requested&&resources.fallback_telemetry_available===false) lines.push(E('p',{},[_('Fallback bandwidth monitoring needs a trusted data source configured on the VPS Agent.')]));
            for(const item of (resources.sources||[]).slice(0,12)) lines.push(E('p',{},[item.source_ip+' · '+item.service+' / '+item.protocol.toUpperCase()+' '+(item.port||'')+' · '+_('Bytes observed')+': '+item.bytes]));
            if(agent.maintenance&&agent.maintenance.state_error) lines.push(E('p',{},[_('Maintenance record storage needs attention; restart actions are disabled.')]));
            const job=s.operation;
            const phases={queued:_('Queued'),accepted:_('Request accepted'),dispatching:_('Restarting'),verifying:_('Verifying recovery'),complete:_('Recovery verified'),failed:_('Operation failed'),uncertain:_('Result unknown'),indeterminate:_('Interrupted; not repeated automatically')};
            if(job) lines.push(E('p',{},[_('Maintenance operation')+': '+(phases[job.phase]||job.phase)+(job.error?' · '+message(job.error):'')]));
            const pending=job&&!['complete','failed','indeterminate'].includes(job.phase);
            for(const [action,button]of Object.entries(this.actionButtons||{})) button.disabled=!!(this.busy||pending||s.enabled!==true||action!=='preflight'&&!(s.permissions||{})[action]);
            this.status.replaceChildren(...lines);
            this.statusUpdatedAt=performance.now();
        }).catch(()=>{
            this.status.className='alert-message warning';
            this.status.replaceChildren(E('strong',{},[_('Cannot read synchronization status; retrying automatically.')]));
            for (const button of Object.values(this.actionButtons||{})) button.disabled=true;
        }).finally(()=>{this.statusRequest=null;});
        return this.statusRequest;
    },
    render:function() {
        const m=this.map=new form.Map(configName,null,
            _('Synchronize your household public IP and inspect VPS service health through direct HTTPS or Cloudflare. Proxy traffic connects directly to the VPS.'));
        let s=m.section(form.NamedSection,'main','access',_('Connection settings'));
        s.addremove=false;
        let o=s.option(form.Flag,'enabled',_('Synchronize with the VPS'),
            _('Changes take effect after Save & Apply. Stopping synchronization does not remove VPS rules. Dynamic authorizations expire; configured resource limits and SSH rescue remain in effect.'));
        o.rmempty=false;
        o=s.option(form.ListValue,'transport',_('Control channel'));
        o.value('cloudflare',_('Cloudflare Worker and Tunnel'));
        o.value('direct',_('Direct HTTPS to Agent'));
        o.default='cloudflare';
        o=s.option(form.Flag,'health_guard',_('Require VPS service health before restoring access'),
            _('A missing or failed remote health report withholds the local access permit. Local proxy checks remain required.'));
        o.rmempty=false;
        o=s.option(form.Value,'health_interval',_('VPS health check interval (seconds)'));o.default='10';o.datatype='range(5,60)';o.rmempty=false;
        o=s.option(form.Value,'endpoint',_('Control service HTTPS address'));o.placeholder='https://your-worker.example';o.rmempty=false;o.depends('enabled','1');o.retain=true;
        o=s.option(form.Value,'device_id',_('Device ID'));o.default='home';o.rmempty=false;o.depends('enabled','1');o.retain=true;
        o=s.option(form.Value,'device_token',_('Device secret'),_('Leave empty to keep the paired device secret.'));o.password=true;o.rmempty=true;
        o.cfgvalue=function(){return '';};o.depends('enabled','1');o.retain=true;
        o=s.option(form.Flag,'direct_confirmed',_('I have confirmed the control service uses a direct connection'),
            _('The control request must bypass the proxy. Configure direct routing before enabling synchronization. A detected proxy exit is rejected.'));
        o.rmempty=false;
        o=s.option(form.ListValue,'family',_('Address families'),_('Choose the public address families to authorize dynamically. Removing a family revokes its dynamic lease after the VPS confirms the update; static rules remain independent.'));
        o.value('ipv4',_('IPv4'));o.value('ipv6',_('IPv6'));o.value('both',_('IPv4 and IPv6'));o.default='ipv4';
        for(const item of [['interval',_('Synchronization interval (seconds)'),300,60,3600],
            ['ttl',_('Dynamic lease duration (seconds)'),900,120,86400],['timeout',_('Control request timeout (seconds)'),8,2,15]]) {
            o=s.option(form.Value,item[0],item[1]);o.default=String(item[2]);o.datatype='range('+item[3]+','+item[4]+')';o.rmempty=false;
        }
        s=m.section(form.NamedSection,'main','access',_('VPS service rules'),
            _('Only selected service ports are managed. Other ports keep the existing system firewall policy. SSH management is separate and disabled by default.')+' '+_('Only add ports you intend to filter. Selecting a panel, API, or subscription port filters that service too. Services sharing the same IP, protocol, and port cannot be separated by URL path or SNI here. SSH has separate settings.'));
        o=s.option(form.Flag,'policy_enabled',_('Enable VPS access rules'));
        o.default='1';o.rmempty=false;
        o=s.option(form.Flag,'policy_confirm',_('Confirm VPS policy changes before keeping them'));
        o.default='1';o.rmempty=false;o.description=_('Recommended. The VPS restores its previous selected-port policy if a changed policy is not confirmed. Disabling this applies changes immediately.');
        o=s.option(form.Value,'policy_confirm_seconds',_('VPS confirmation window (seconds)'));o.default='60';o.datatype='range(30,300)';o.rmempty=false;o.depends('policy_confirm','1');
        o=s.option(form.ListValue,'protection_mode',_('Default port protection mode'));
        o.value('standard',_('Standard resource protection'));o.value('whitelist',_('Whitelist only'));o.value('observe',_('Observe only'));o.default='standard';o.rmempty=false;
        s=m.section(form.GridSection,'rule',_('Services'),
            _('Discovery lists candidate ports only. Whitelist mode requires an authorized source; standard mode applies resource limits; observe mode records without blocking. Unrestricted rules keep the original system firewall behavior.')+' '+_('Each rule has its own mode, sources, thresholds and timers. Ports grouped in one rule share these settings. Create separate rules for different settings.'));
        s.addremove=true;s.anonymous=false;s.sortable=false;s.nodescriptions=true;
        o=s.option(form.Flag,'enabled',_('Enabled'));o.default='1';o.rmempty=false;
        o=s.option(form.Value,'name',_('Service name'));o.rmempty=false;o.datatype='maxlength(64)';
        o=s.option(form.ListValue,'protocol',_('Protocol'));o.value('tcp','TCP');o.value('udp','UDP');o.value('both','TCP + UDP');o.default='tcp';o.textvalue=function(section){return {tcp:'TCP',udp:'UDP',both:'TCP + UDP'}[this.cfgvalue(section)||'tcp'];};
        o=s.option(form.ListValue,'protection_mode',_('Port protection mode'));
        o.value('inherit',_('Use default mode'));o.value('whitelist',_('Whitelist only'));o.value('standard',_('Standard resource protection'));o.value('observe',_('Observe only'));o.default='inherit';o.rmempty=false;
        o.textvalue=function(section){return effectLabel(uci.get(configName,section)||{});};
        o=s.option(form.DynamicList,'ports',_('Ports'));o.placeholder='443';o.rmempty=false;
        o.validate=function(section,value) {
            const ports=Array.isArray(value)?value:[value];
            return ports.length&&ports.every(p=>{
                const match=/^([1-9][0-9]{0,4})(?:-([1-9][0-9]{0,4}))?$/.exec(p||'');
                return match&&Number(match[1])<=Number(match[2]||match[1])&&Number(match[2]||match[1])<=65535;
            })||_('Enter ports from 1 to 65535, or a port range.');
        };
        o=s.option(form.ListValue,'source_mode',_('Allowed or exempt sources'),_('All sources keeps standard resource limits active. Household and static addresses are allowed in whitelist mode and exempt from standard limits. Legacy bypass disables this rule protection.'));
        o.value('all',_('All sources, resource limits apply'));o.value('any',_('Bypass all protection (legacy behavior)'));o.value('dynamic',_('Household public IP'));
        o.value('static',_('Static whitelist'));o.value('mixed',_('Household IP and static whitelist'));o.default='dynamic';o.textvalue=function(section){return sourceLabels()[this.cfgvalue(section)||'dynamic'];};
        o=s.option(form.DynamicList,'sources',_('Static IP addresses or networks'));
        o.datatype='ipaddr';o.depends('source_mode','static');o.depends('source_mode','mixed');o.retain=true;
        for(const item of [['rate_enabled',_('Limit new connection rate'),true],['connections_enabled',_('Limit concurrent connections'),true],['bandwidth_enabled',_('Limit verified fallback bandwidth'),false]]) {
            o=s.option(form.Flag,item[0],item[1]);o.default=item[2]?'1':'0';o.rmempty=false;o.modalonly=true;
        }
        for(const item of [['rate',_('New connections per second'),40,1,10000],['burst',_('Connection burst allowance'),80,1,20000],['connections',_('Concurrent connection limit'),128,1,10000],['bandwidth',_('Fallback bandwidth per direction (bytes per second)'),1048576,1024,1073741824],['sustain',_('Bandwidth threshold duration (seconds)'),10,1,300],['cooldown',_('New connection cooldown (seconds)'),30,1,3600],['window',_('Observation window (seconds)'),60,5,600]]) {
            o=s.option(form.Value,item[0],item[1]);o.default=String(item[2]);o.datatype='range('+item[3]+','+item[4]+')';o.rmempty=false;o.modalonly=true;
        }
        s=m.section(form.NamedSection,'main','access',_('Independent proxy heartbeat'),_('Use an Agent HTTPS endpoint reached through the local SOCKS proxy, separately from the control channel.'));
        o=s.option(form.Flag,'path_watch',_('Enable proxy-path heartbeat'));o.rmempty=false;
        o=s.option(form.Value,'path_endpoint',_('Agent HTTPS address through the proxy'));o.depends('path_watch','1');o.retain=true;
        o=s.option(form.Value,'path_token',_('Proxy heartbeat secret'),_('Leave empty to keep the paired secret.'));o.password=true;o.cfgvalue=()=>'';o.depends('path_watch','1');o.retain=true;
        o=s.option(form.Value,'path_interval',_('Proxy heartbeat interval (seconds)'));o.default='10';o.datatype='range(5,60)';o.rmempty=false;o.depends('path_watch','1');
        s=m.section(form.NamedSection,'main','access',_('SSH management'),_('SSH authentication settings remain unchanged. Access is managed only after both heartbeats and an authorized SSH session are verified.'));
        o=s.option(form.Flag,'ssh_managed',_('Manage SSH access'));o.rmempty=false;
        o=s.option(form.Value,'ssh_port',_('SSH port'));o.default='22';o.datatype='port';o.rmempty=false;o.depends('ssh_managed','1');
        o=s.option(form.DynamicList,'ssh_managers',_('Management IP addresses or networks'));o.datatype='ipaddr';o.depends('ssh_managed','1');o.retain=true;
        o=s.option(form.Flag,'ssh_confirmed',_('I have verified an authorized SSH management session'));o.rmempty=false;o.depends('ssh_managed','1');
        o=s.option(form.Flag,'ssh_rescue',_('Enable emergency SSH access'));o.default='1';o.rmempty=false;o.depends('ssh_managed','1');
        o=s.option(form.Value,'ssh_after',_('Both heartbeats lost for (seconds)'));o.default='60';o.datatype='range(10,3600)';o.rmempty=false;o.depends({ssh_managed:'1',ssh_rescue:'1'});
        o=s.option(form.ListValue,'ssh_scope',_('Emergency source scope'));o.value('public',_('Public Internet'));o.value('restricted',_('Management addresses and last household IP'));o.default='public';o.rmempty=false;o.depends({ssh_managed:'1',ssh_rescue:'1'});
        o=s.option(form.Value,'ssh_open_seconds',_('Public emergency window (seconds)'));
        o.default='0';o.datatype='uinteger';o.rmempty=false;o.depends({ssh_managed:'1',ssh_rescue:'1',ssh_scope:'public'});
        o.validate=(section,value)=>/^\d+$/.test(value||'')&&(Number(value)===0||Number(value)>=30&&Number(value)<=3600)||_('Enter 0 to keep rescue open, or an integer from 30 to 3600 seconds.');
        o.description=_('0 keeps emergency SSH open until household authorization is restored. Use 30 to 3600 for a timed window.')+' '+_('Warning: a timed window closes public access when it expires. If your IP has changed and no allowed management source is reachable, you may lose SSH access. An unlimited window keeps SSH publicly reachable during the outage; SSH authentication and the system firewall still apply.');
        s=m.section(form.NamedSection,'main','access',_('Remote maintenance'),_('The VPS Agent must also explicitly allow each action. A request being accepted does not mean recovery is complete.'));
        o=s.option(form.Flag,'allow_restart',_('Allow restarting the proxy core'));o.rmempty=false;
        o=s.option(form.Flag,'allow_reboot',_('Allow rebooting the VPS'));o.rmempty=false;
        o=s.option(form.Value,'maintenance_timeout',_('Recovery verification timeout (seconds)'));o.default='180';o.datatype='range(30,600)';o.rmempty=false;
        this.statusUpdatedAt=performance.now();
        this.status=E('div',{id:'pg-access-status',class:'alert-message notice',role:'status','aria-live':'polite'},[_('Waiting to synchronize')]);
        return m.render().then(node=>{
            this.refresh();poll.add(()=>this.refresh(),5);setTimeout(()=>pgTrial.attach(this),0);
            this.actionButtons={};
            const actions=E('div',{class:'cbi-page-actions'},[]);
            for(const [action,label]of [['preflight',_('Check management readiness')],['restart_xray',_('Restart proxy core')],['reboot_vps',_('Reboot VPS')]]) {
                const button=E('button',{class:'cbi-button '+(action==='preflight'?'cbi-button-neutral':'cbi-button-action'),type:'button',disabled:true,click:()=>this.confirmAction(action,label)},[label]);
                this.actionButtons[action]=button;actions.appendChild(button);
            }
            actions.appendChild(E('button',{class:'cbi-button cbi-button-neutral',type:'button',click:()=>this.preparePolicyRelease()},[_('Prepare to remove VPS rules')]));
            const preview=E('button',{class:'cbi-button cbi-button-neutral',type:'button',click:()=>this.previewRules()},[_('Preview service rules')]);actions.appendChild(preview);actions.appendChild(E('a',{class:'cbi-button',href:'proxy-guard-access-raw'},[_('Raw UCI configuration')]));
            return pgI18n.decorate(E('div',{},[E('h2',{},[_('VPS access rules')]),this.status,node,actions]));
        });
    },
    reloadAccessConfig:function(){uci.unload(configName);return this.map.load().then(()=>this.map.reset()).then(()=>ui.changes.init());},
    preparePolicyRelease:function(){
        pgI18n.modal(ui,_('Remove VPS rules'),[E('p',{},[_('Prepare to turn off this plugin VPS port rules and SSH management while synchronization remains enabled. Save & Apply, then confirm the VPS change. After the VPS confirms removal you may stop synchronization. The system firewall remains in effect.')]),E('div',{class:'right'},[
            E('button',{type:'button',class:'cbi-button',click:ui.hideModal},[_('Cancel')]),
            E('button',{type:'button',class:'cbi-button cbi-button-action',click:()=>{ui.hideModal();return this.map.parse().then(()=>{uci.set(configName,'main','enabled','1');uci.set(configName,'main','policy_enabled','0');uci.set(configName,'main','ssh_managed','0');return this.map.load();}).then(()=>this.map.reset()).then(()=>ui.showIndicator('pg-access-draft',_('Unsaved changes'))).catch(e=>ui.addNotification(null,E('p',{},[e.message]),'error'));}},[_('Prepare changes')])])]);
    },
    confirmAction:function(action,label) {
        if(action==='preflight') return this.sendAction(action);
        pgI18n.modal(ui,label,[E('p',{},[_('This interrupts proxy access. Local protection is prepared before the request is sent.')]),E('div',{class:'right'},[
            E('button',{class:'cbi-button',click:ui.hideModal},[_('Cancel')]),
            E('button',{class:'cbi-button cbi-button-negative',click:()=>{ui.hideModal();this.sendAction(action);}},[_('Confirm')])])]);
    },
    sendAction:function(action) {
        if(this.busy)return Promise.resolve();this.busy=true;
        return actionCalls[action]().then(result=>{
            if(!result.ok)throw new Error(message(result.error));
            return this.refresh();
        }).catch(error=>ui.addNotification(null,E('p',{},[error.message||_('Operation failed')]),'error')).finally(()=>{this.busy=false;this.refresh();});
    },
    previewRules:function() {
        return this.map.parse().then(()=>{
            const rows=[E('tr',{},[_('Service name'),_('Protocol'),_('Ports'),_('Port protection mode'),_('IP filtering'),_('Static IP addresses or networks')].map(label=>E('th',{},[label])))];
            const sourceModes=sourceLabels();
            uci.sections(configName,'rule',rule=>{if(rule.enabled!=='0') rows.push(E('tr',{},[
                E('td',{},[rule.name||rule['.name']]),E('td',{},[(rule.protocol||'tcp').toUpperCase()]),
                E('td',{},[(Array.isArray(rule.ports)?rule.ports:[rule.ports||'']).join(', ')]),
                E('td',{},[effectLabel(rule)]),
                E('td',{},[sourceModes[rule.source_mode||'dynamic']]),E('td',{},[(Array.isArray(rule.sources)?rule.sources:[]).join(', ')])]));});
            pgI18n.modal(ui,_('Service rule preview'),[E('p',{},[_('This preview has not been applied. Unselected ports keep the existing system firewall policy.')]),
                E('table',{class:'table'},rows),E('div',{class:'right'},[E('button',{class:'cbi-button',click:ui.hideModal},[_('Close')])])]);
        }).catch(error=>ui.addNotification(null,E('p',{},[error.message]),'error'));
    },
    handleSave:function(){return this.map.save().then(()=>{ui.hideIndicator('pg-access-draft');return ui.changes.init();});},
    handleReset:function(){ui.hideIndicator('pg-access-draft');return this.map.reset();},
    handleSaveApply:function(){
        return this.map.save().then(()=>applyCall()).then(result=>{
            if(!result.ok) throw new Error(message(result.error));
            ui.hideIndicator('pg-access-draft');pgTrial.begin(result.policy_trial);
            return Promise.all([this.refresh(),ui.changes.init()]);
        }).catch(error=>ui.addNotification(null,E('p',{},[error.message||_('Apply failed')]),'error'));
    }
});
