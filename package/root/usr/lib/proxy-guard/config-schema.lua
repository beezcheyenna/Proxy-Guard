-- Fixed plugin schemas. Unknown values stay editable, but never silently valid.
local M={}
local function words(text)local out={};for key in text:gmatch('%S+')do out[key]=true end;return out end
local core=words([[check_mode web_sensitive_interval public_hb_interval public_hb_timeout public_hb_fail public_hb_recover public_hb_sensitive_interval diagnostics_enabled diagnostics_interval diagnostics_ttl exit_provider api_enabled api_default_seconds api_max_seconds enabled setup_complete mode interfaces sources4 sources6 ipv6_protect local4 local6 proxy_ports dns_ports targets socks_port proxy_client client_auto_ports passwall_watch passwall_log_watch passwall_log_interval boot_guard passwall_trigger fast_wait_enabled fast_wait_seconds fast_stable_enabled fast_stable_seconds schedule_enabled schedule_start schedule_end schedule_utc_offset schedule_repeat schedule_weekdays exit_check expected_exit4 exit_url exit_fallback_url interval timeout fail_threshold recover_threshold startup_grace min_success log_kib debug self_heal self_heal_stale self_heal_cooldown self_heal_limit self_heal_window resource_monitor udp_check udp_server udp_port udp_query udp_timeout]])
function M.assess(name,sections,resolved)
 assert(name=='proxy_guard','raw_target_invalid')
 local unknown={}
 for id,section in pairs(sections)do
  local allowed=core
  for key in pairs(section.options)do
   -- Old Cloudflare startup checks are retired. Preserve the saved option.
   if not allowed[key] and not (id=='main' and key=='cf_event_check') and #unknown<32 then
    unknown[#unknown+1]=id..'.'..key
   end
  end
 end
 table.sort(unknown)
 local values=resolved or {};for id,section in pairs(resolved and {} or sections)do
  local row={['.type']=section.section_type};for k,v in pairs(section.options)do row[k]=v end;values[id]=row
 end
 local active=values.main.enabled=='1'
 local requested={};for k,v in pairs(values.main)do requested[k]=v end;requested.enabled='1';values.main=requested
 local ok,error=pcall(function()
  require('proxy-guard.core').load_config(values.main)
 end)
 return {syntax_valid=true,enabled=active,activation_parameters_valid=ok,
  activation_error=not ok and(tostring(error):match('([a-z_]+)$')or'activation_parameters_invalid')or nil,
  unknown_fields=unknown,ignored_fields={}}
end
return M
