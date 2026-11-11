-- Fixed plugin schemas. Unknown values stay editable, but never silently valid.
local M={}
local function words(text)local out={};for key in text:gmatch('%S+')do out[key]=true end;return out end
local core=words([[enabled setup_complete mode interfaces sources4 sources6 ipv6_protect local4 local6 proxy_ports dns_ports targets socks_port proxy_client client_auto_ports passwall_watch passwall_log_watch passwall_log_interval boot_guard passwall_trigger fast_wait_enabled fast_wait_seconds fast_stable_enabled fast_stable_seconds schedule_enabled schedule_start schedule_end schedule_utc_offset schedule_repeat schedule_weekdays exit_check exit_source expected_exit4 exit_url exit_fallback_url cf_event_check interval timeout fail_threshold recover_threshold startup_grace min_success log_kib debug self_heal self_heal_stale self_heal_cooldown self_heal_limit self_heal_window resource_monitor udp_check udp_server udp_port udp_query udp_timeout]])
local main=words([[enabled policy_enabled default_deny auto_discover endpoint transport health_interval health_guard device_id direct_confirmed family interval ttl timeout revision protection_mode path_watch path_endpoint path_interval device_token path_token allow_restart allow_reboot maintenance_timeout ssh_managed ssh_confirmed ssh_port ssh_rescue ssh_after ssh_scope ssh_open_seconds ssh_managers policy_confirm policy_confirm_seconds]])
local rule=words([[enabled name protocol ports protection_mode source_mode sources rate_enabled rate burst connections_enabled connections bandwidth_enabled bandwidth sustain cooldown window]])
function M.assess(name,sections,resolved)
 local unknown,ignored={},{}
 for id,section in pairs(sections)do
  local allowed=name=='proxy_guard'and core or id=='main'and main or rule
  for key in pairs(section.options)do
   if not allowed[key]and #unknown<32 then unknown[#unknown+1]=id..'.'..key end
   if name=='proxy_guard_access'and id=='main'and (key=='default_deny'or key=='auto_discover')and section.options[key]~='0'then ignored[#ignored+1]=id..'.'..key end
  end
 end
 table.sort(unknown);table.sort(ignored)
 local values=resolved or {};for id,section in pairs(resolved and {} or sections)do
  local row={['.type']=section.section_type};for k,v in pairs(section.options)do row[k]=v end;values[id]=row
 end
 local active=values.main.enabled=='1'
 local requested={};for k,v in pairs(values.main)do requested[k]=v end;requested.enabled='1';values.main=requested
 local ok,error=pcall(function()
  if name=='proxy_guard'then require('proxy-guard.core').load_config(values.main)
  else require('proxy-guard.access').load(values)end
 end)
 return {syntax_valid=true,enabled=active,activation_parameters_valid=ok,
  activation_error=not ok and(tostring(error):match('([a-z_]+)$')or'activation_parameters_invalid')or nil,
  unknown_fields=unknown,ignored_fields=ignored}
end
return M
