import { resolve } from './clients.uc';
print(sprintf('%J\n',resolve(ARGV[0] || 'auto')));
