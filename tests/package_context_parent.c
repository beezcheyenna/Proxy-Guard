#include <unistd.h>
#include <stdlib.h>
#include <sys/wait.h>
int main(void) {
 if (access("/etc/pgvm-fixture",F_OK)) return 99;
 const char *script=getenv("PG_CONTEXT_SCRIPT");
 if (!script) return 98;
 pid_t child=fork();
 if (child<0) return 97;
 if (!child) {execl("/usr/bin/ucode","ucode",script,(char *)0);_exit(96);}
 int status;
 if (waitpid(child,&status,0)<0) return 95;
 return WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
}
