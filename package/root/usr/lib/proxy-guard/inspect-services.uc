import { services } from './services.uc';
let profile=null;
if (ARGV[1]) { try { profile=json(ARGV[1]); } catch(e) {} }
print(sprintf('%J\n',services(ARGV[0] || 'dnsmasq',profile)));
