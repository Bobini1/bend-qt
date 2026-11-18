// The per-user cache of bundled Qt runtimes and decoded native modules lives
// in $XDG_CACHE_HOME/bend-qt or ~/.cache/bend-qt. Each entry is a private
// directory named by a 64-digit content identity. A program holds a shared
// lock on each entry's .use file for its lifetime and refreshes the file's time
// when it starts. At most once a day a starting program removes the entries
// that have not been used for a week and that no running program holds.
//
// Every C file that uses the cache includes these helpers; the first copy in a
// file defines them. Package generation keeps their names unprefixed.
#ifndef BQT_CACHE_HELPERS
#define BQT_CACHE_HELPERS
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/syscall.h>
#include <fcntl.h>
#include <unistd.h>
#include <limits.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <time.h>

#define BQT_CACHE_UNUSED_SECONDS (7*24*3600)
#define BQT_CACHE_COLLECT_SECONDS (24*3600)
#define BQT_CACHE_HELPER __attribute__((unused)) static

static char bqt_cache_message[PATH_MAX + 256];
BQT_CACHE_HELPER const char *bqt_cache_fail(const char *what, const char *path) {
    snprintf(bqt_cache_message,sizeof bqt_cache_message,"Cannot prepare the Qt cache (%s): %s: %s",what,path,strerror(errno));
    return bqt_cache_message;
}
BQT_CACHE_HELPER int bqt_cache_private_dir(const char *path) {
    if(mkdir(path,0700)&&errno!=EEXIST)return -1;
    int fd=open(path,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return -1;
    struct stat st;
    if(fstat(fd,&st)||st.st_uid!=getuid()||(st.st_mode&077)){close(fd);errno=EACCES;return -1;}
    return fd;
}
BQT_CACHE_HELPER int bqt_cache_regular(int fd) {
    struct stat st;return fd>=0&&!fstat(fd,&st)&&S_ISREG(st.st_mode)&&st.st_uid==getuid();
}
// Creates the private cache directory and writes its path to base.
BQT_CACHE_HELPER const char *bqt_cache_base(char base[PATH_MAX]) {
    const char *cache=getenv("XDG_CACHE_HOME"),*home=getenv("HOME");
    if(cache&&cache[0]=='/') {
        if(snprintf(base,PATH_MAX,"%s",cache)>=PATH_MAX)return "Qt cache path is too long";
    } else {
        if(!home||home[0]!='/')return "Qt needs HOME or an absolute XDG_CACHE_HOME for its cache";
        if(snprintf(base,PATH_MAX,"%s/.cache",home)>=PATH_MAX)return "Qt cache path is too long";
    }
    if(mkdir(base,0700)&&errno!=EEXIST)return bqt_cache_fail("cache directory",base);
    size_t n=strlen(base);
    if(n+sizeof "/bend-qt">PATH_MAX)return "Qt cache path is too long";
    strcpy(base+n,"/bend-qt");int fd=bqt_cache_private_dir(base);
    if(fd<0)return bqt_cache_fail("private cache",base);
    close(fd);return NULL;
}
// Opens the entry base/id and holds it: *use keeps a shared lock on its .use
// file and must stay open while the program uses the entry. *root is the open
// entry directory, which the caller closes.
BQT_CACHE_HELPER const char *bqt_cache_hold(const char *base, const char *id, char path[PATH_MAX], int *root, int *use) {
    *root=*use=-1;
    if(snprintf(path,PATH_MAX,"%s/%s",base,id)>=PATH_MAX)return "Qt cache path is too long";
    for(int attempt=0;attempt<8;attempt++) {
        *root=bqt_cache_private_dir(path);if(*root<0)return bqt_cache_fail("entry",path);
        *use=openat(*root,".use",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
        if(!bqt_cache_regular(*use)||flock(*use,LOCK_SH)) {
            if(*use>=0)close(*use);close(*root);*root=*use=-1;return bqt_cache_fail("use lock",path);
        }
        // Collection renames an unused entry before removing it. A program
        // that waited for it starts over on a fresh directory.
        struct stat held,named;
        if(!fstat(*root,&held)&&!lstat(path,&named)&&held.st_dev==named.st_dev&&held.st_ino==named.st_ino)break;
        close(*use);close(*root);*root=*use=-1;
    }
    if(*root<0)return "A Qt cache entry kept moving during startup";
    // The .use file's time records the last start; a non-empty file has one.
    struct stat used;
    if(!fstat(*use,&used)&&used.st_size==0&&write(*use,"\n",1)!=1) {
        close(*use);close(*root);*root=*use=-1;return bqt_cache_fail("use time",path);
    }
    futimens(*use,NULL);
    return NULL;
}
// An exclusive lock for completing an entry, or -1.
BQT_CACHE_HELPER int bqt_cache_lock(int root) {
    int lock=openat(root,".lock",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
    if(!bqt_cache_regular(lock)||flock(lock,LOCK_EX)){if(lock>=0)close(lock);return -1;}
    return lock;
}
// A complete entry records .ready: one line describing the files it vouches
// for. The line includes their inodes, sizes, modes and modification times, so
// a start that reproduces it can trust the files without reading them.
BQT_CACHE_HELPER int bqt_cache_ready(int root, const char *record) {
    char recorded[257];size_t n=strlen(record);
    int fd=openat(root,".ready",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return 0;
    ssize_t got=read(fd,recorded,sizeof recorded);close(fd);
    return n<sizeof recorded&&got==(ssize_t)n&&!memcmp(recorded,record,n);
}
BQT_CACHE_HELPER const char *bqt_cache_mark(int root, const char *record, const char *path) {
    char temp[64];size_t n=strlen(record);
    // Content reaches the disk before the stamp that vouches for it.
    if(syscall(SYS_syncfs,root))return bqt_cache_fail("sync",path);
    snprintf(temp,sizeof temp,".ready-%ld",(long)getpid());unlinkat(root,temp,0);
    int fd=openat(root,temp,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if(fd<0)return bqt_cache_fail("stamp",path);
    int failed=write(fd,record,n)!=(ssize_t)n;close(fd);
    if(failed||renameat(root,temp,root,".ready")){unlinkat(root,temp,0);return bqt_cache_fail("stamp",path);}
    return NULL;
}
BQT_CACHE_HELPER void bqt_cache_remove_tree(int parent, const char *name, int depth) {
    for(int pass=0;pass<2&&depth<64;pass++) {
        int fd=openat(parent,name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)break;
        DIR *entries=fdopendir(fd);if(!entries){close(fd);break;}
        struct dirent *entry;
        while((entry=readdir(entries))) {
            if(!strcmp(entry->d_name,".")||!strcmp(entry->d_name,".."))continue;
            if(unlinkat(dirfd(entries),entry->d_name,0)&&(errno==EISDIR||errno==EPERM))
                bqt_cache_remove_tree(dirfd(entries),entry->d_name,depth+1);
        }
        closedir(entries);
        if(!unlinkat(parent,name,AT_REMOVEDIR)||errno!=ENOTEMPTY)break;
    }
}
BQT_CACHE_HELPER int bqt_cache_entry_name(const char *name) {
    if(strlen(name)!=64)return 0;
    for(const char *p=name;*p;p++)if(!((*p>='0'&&*p<='9')||(*p>='a'&&*p<='f')))return 0;
    return 1;
}
// Removes unused entries; entries this program holds are locked. Runs once per
// file that includes it, and at most once a day across all programs.
BQT_CACHE_HELPER void bqt_cache_collect(const char *base) {
    static int checked;if(checked)return;checked=1;
    int dir=open(base,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if(dir<0)return;
    int stamp=openat(dir,".collected",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
    struct stat st;time_t now=time(NULL);
    // An empty stamp has never recorded a collection.
    if(stamp<0||fstat(stamp,&st)||!S_ISREG(st.st_mode)||flock(stamp,LOCK_EX|LOCK_NB)
       ||(st.st_size>0&&now-st.st_mtime<BQT_CACHE_COLLECT_SECONDS)) {
        if(stamp>=0)close(stamp);close(dir);return;
    }
    if(st.st_size==0&&write(stamp,"\n",1)!=1){close(stamp);close(dir);return;}
    futimens(stamp,NULL);
    int listing=dup(dir);DIR *entries=listing<0?NULL:fdopendir(listing);
    if(!entries){if(listing>=0)close(listing);close(stamp);close(dir);return;}
    struct dirent *entry;
    while((entry=readdir(entries))) {
        const char *name=entry->d_name;
        if(!strncmp(name,".trash-",7)){bqt_cache_remove_tree(dir,name,0);continue;}
        if(!bqt_cache_entry_name(name))continue;
        int child=openat(dir,name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if(child<0)continue;
        // Read the directory's time before .use might be created in it.
        struct stat cs,us;int use=-1;
        int keep=fstat(child,&cs)||cs.st_uid!=getuid()
                 ||(use=openat(child,".use",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600))<0
                 ||fstat(use,&us)||!S_ISREG(us.st_mode)
                 ||now-(us.st_size?us.st_mtime:cs.st_mtime)<BQT_CACHE_UNUSED_SECONDS
                 ||flock(use,LOCK_EX|LOCK_NB);
        if(!keep) {
            // Renaming first lets a program that is starting on this entry
            // notice and start over on a fresh one.
            char trash[NAME_MAX+1];snprintf(trash,sizeof trash,".trash-%.20s-%ld",name,(long)getpid());
            if(!renameat(dir,name,dir,trash)){close(use);use=-1;bqt_cache_remove_tree(dir,trash,0);}
        }
        if(use>=0)close(use);close(child);
    }
    closedir(entries);close(stamp);close(dir);
}
#endif
