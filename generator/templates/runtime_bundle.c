// Matching Qt runtime assets, carried by ordinary foreign C imports.
// @TYPES@
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
#include <dlfcn.h>

typedef struct BqtBundleFile {
    const char *path;
    size_t size;
    unsigned mode;
    const char *sha256;
    size_t first, count;
    uint64_t modules[2];
} BqtBundleFile;
static const BqtBundleFile bqt_bundle_files[] = {
// @FILES@
};
static const struct { const char *path; size_t target; } bqt_bundle_aliases[] = {
// @ALIASES@
};
static const BqtBundleBlock *bqt_bundle_blocks[@BLOCK_COUNT@ + 1];
static int bqt_bundle_invalid;
static uint64_t bqt_bundle_active[2] = @ACTIVE_MODULES@;
static const char *const bqt_bundle_module_names[] = {@MODULE_NAMES@};
static char bqt_bundle_root[PATH_MAX], bqt_bundle_error[PATH_MAX + 256];
void bqt_bundle_enable(size_t index) {
    if (index >= @MODULE_COUNT@) bqt_bundle_invalid = 1;
    else bqt_bundle_active[index / 64] |= UINT64_C(1) << (index % 64);
}
static int bqt_bundle_selected(const BqtBundleFile *file) {
    return (file->modules[0] & bqt_bundle_active[0]) || (file->modules[1] & bqt_bundle_active[1]);
}
static int bqt_bundle_contains(const char *relative) {
    for (size_t i = 0; i < @FILE_COUNT@; ++i)
        if (!strcmp(relative, bqt_bundle_files[i].path)) return bqt_bundle_selected(&bqt_bundle_files[i]);
    for (size_t i = 0; i < @ALIAS_COUNT@; ++i)
        if (!strcmp(relative, bqt_bundle_aliases[i].path))
            return bqt_bundle_selected(&bqt_bundle_files[bqt_bundle_aliases[i].target]);
    return 0;
}
void bqt_bundle_add(size_t index, const BqtBundleBlock *block) {
    if (index >= @BLOCK_COUNT@ || bqt_bundle_blocks[index]) bqt_bundle_invalid = 1;
    else bqt_bundle_blocks[index] = block;
}
#ifndef BQT_BUNDLE_STANDALONE
static void __attribute__((constructor)) bqt_bundle_link(void) {
// @REFERENCES@
}
#endif

#ifdef CID(native_Runtime_bundleHost)
static Term bqt_bundle_host_run(Env e, Term *f, IoWork *w) { return term_pak(CID(Unit), 0); }
static void __attribute__((constructor)) bqt_bundle_host_register(void) {
    io_eff(CID(native_Runtime_bundleHost), bqt_bundle_host_run);
}
#endif

// SHA-256 verifies both cached files and freshly decoded data. Qt's runtime
// does not acquire an additional crypto-library dependency for extraction.
typedef struct { uint32_t h[8]; uint64_t bytes; unsigned char tail[64]; } BqtSha256;
static uint32_t bqt_sha_rotr(uint32_t x, unsigned n) { return x >> n | x << (32 - n); }
static void bqt_sha_block(BqtSha256 *s, const unsigned char *p) {
    static const uint32_t k[64] = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    uint32_t w[64];
    for (unsigned i=0;i<16;i++) w[i]=(uint32_t)p[i*4]<<24|(uint32_t)p[i*4+1]<<16|(uint32_t)p[i*4+2]<<8|p[i*4+3];
    for (unsigned i=16;i<64;i++) {
        uint32_t a=w[i-15], b=w[i-2];
        w[i]=w[i-16]+(bqt_sha_rotr(a,7)^bqt_sha_rotr(a,18)^(a>>3))+w[i-7]+(bqt_sha_rotr(b,17)^bqt_sha_rotr(b,19)^(b>>10));
    }
    uint32_t a=s->h[0],b=s->h[1],c=s->h[2],d=s->h[3],e=s->h[4],f=s->h[5],g=s->h[6],h=s->h[7];
    for (unsigned i=0;i<64;i++) {
        uint32_t t=h+(bqt_sha_rotr(e,6)^bqt_sha_rotr(e,11)^bqt_sha_rotr(e,25))+((e&f)^(~e&g))+k[i]+w[i];
        uint32_t u=(bqt_sha_rotr(a,2)^bqt_sha_rotr(a,13)^bqt_sha_rotr(a,22))+((a&b)^(a&c)^(b&c));
        h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u;
    }
    uint32_t v[8]={a,b,c,d,e,f,g,h};for(unsigned i=0;i<8;i++)s->h[i]+=v[i];
}
static void bqt_sha_init(BqtSha256 *s) {
    *s=(BqtSha256){{0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19},0,{0}};
}
static void bqt_sha_update(BqtSha256 *s, const unsigned char *p, size_t n) {
    while(n) {
        size_t used=s->bytes%64, take=64-used;if(take>n)take=n;
        memcpy(s->tail+used,p,take);s->bytes+=take;p+=take;n-=take;
        if(s->bytes%64==0)bqt_sha_block(s,s->tail);
    }
}
static void bqt_sha_finish(BqtSha256 *s, char out[65]) {
    uint64_t bits=s->bytes*8;unsigned char end[128]={0x80};
    size_t n=64-(s->bytes%64);if(n<9)n+=64;
    for(unsigned i=0;i<8;i++)end[n-1-i]=(unsigned char)(bits>>(i*8));
    bqt_sha_update(s,end,n);
    for(unsigned i=0;i<8;i++)snprintf(out+i*8,9,"%08x",s->h[i]);
}
static int bqt_bundle_matches(int fd, const BqtBundleFile *file) {
    struct stat st;
    if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<0||(uint64_t)st.st_size!=file->size
       ||(st.st_mode&0777)!=file->mode||lseek(fd,0,SEEK_SET)<0)return 0;
    BqtSha256 sha;bqt_sha_init(&sha);unsigned char buf[65536];ssize_t n;
    while((n=read(fd,buf,sizeof buf))!=0) {
        if(n<0){if(errno==EINTR)continue;return 0;}bqt_sha_update(&sha,buf,(size_t)n);
    }
    char digest[65];bqt_sha_finish(&sha,digest);return !strcmp(digest,file->sha256);
}
static const char *bqt_bundle_fail(const char *what, const char *path) {
    snprintf(bqt_bundle_error,sizeof bqt_bundle_error,"Cannot prepare bundled Qt (%s): %s: %s",what,path,strerror(errno));
    return bqt_bundle_error;
}
// Every component below the private cache root is opened without following
// symlinks. File paths are normalized and checked by the generator.
static int bqt_bundle_parent(int root, const char *path, char name[NAME_MAX+1]) {
    char copy[PATH_MAX];if(strlen(path)>=sizeof copy){errno=ENAMETOOLONG;return -1;}
    strcpy(copy,path);int parent=dup(root);if(parent<0)return -1;
    char *cursor=copy,*slash;
    while((slash=strchr(cursor,'/'))) {
        *slash=0;if(mkdirat(parent,cursor,0700)&&errno!=EEXIST){close(parent);return -1;}
        int next=openat(parent,cursor,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);close(parent);
        if(next<0)return -1;parent=next;cursor=slash+1;
    }
    if(strlen(cursor)>NAME_MAX){close(parent);errno=ENAMETOOLONG;return -1;}
    strcpy(name,cursor);return parent;
}
static int bqt_bundle_private_dir(const char *path) {
    if(mkdir(path,0700)&&errno!=EEXIST)return -1;
    int fd=open(path,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return -1;
    struct stat st;
    if(fstat(fd,&st)||st.st_uid!=getuid()||(st.st_mode&077)){close(fd);errno=EACCES;return -1;}
    return fd;
}
static int bqt_bundle_digit(unsigned char c) {
    if(c>='A'&&c<='Z')return c-'A';if(c>='a'&&c<='z')return c-'a'+26;
    if(c>='0'&&c<='9')return c-'0'+52;if(c=='+')return 62;if(c=='/')return 63;return -1;
}

// A verified runtime directory records .ready: a digest of every selected
// file's path, inode, size, mode and modification time. A start whose stat
// results reproduce it skips hashing the content. Writing a file, changing
// its mode or replacing it changes the digest, and the next start verifies
// and repairs the directory by content again.
static void bqt_bundle_stat_update(BqtSha256 *s, const char *path, const struct stat *st) {
    uint64_t fields[6]={(uint64_t)st->st_dev,(uint64_t)st->st_ino,(uint64_t)st->st_size,(uint64_t)st->st_mode,
                        (uint64_t)st->st_mtim.tv_sec,(uint64_t)st->st_mtim.tv_nsec};
    bqt_sha_update(s,(const unsigned char*)path,strlen(path)+1);
    bqt_sha_update(s,(const unsigned char*)fields,sizeof fields);
}
static int bqt_bundle_signature(int root, const char *identity, char out[65]) {
    BqtSha256 s;bqt_sha_init(&s);bqt_sha_update(&s,(const unsigned char*)identity,64);
    for(size_t i=0;i<@FILE_COUNT@;i++) {
        const BqtBundleFile *file=&bqt_bundle_files[i];struct stat st;
        if(!bqt_bundle_selected(file))continue;
        if(fstatat(root,file->path,&st,AT_SYMLINK_NOFOLLOW)||!S_ISREG(st.st_mode)
           ||(uint64_t)st.st_size!=file->size||(st.st_mode&0777)!=file->mode)return 0;
        bqt_bundle_stat_update(&s,file->path,&st);
    }
    for(size_t i=0;i<@ALIAS_COUNT@;i++) {
        const BqtBundleFile *file=&bqt_bundle_files[bqt_bundle_aliases[i].target];struct stat a,b;
        if(!bqt_bundle_selected(file))continue;
        if(fstatat(root,bqt_bundle_aliases[i].path,&a,AT_SYMLINK_NOFOLLOW)||fstatat(root,file->path,&b,AT_SYMLINK_NOFOLLOW)
           ||!S_ISREG(a.st_mode)||a.st_dev!=b.st_dev||a.st_ino!=b.st_ino)return 0;
        bqt_bundle_stat_update(&s,bqt_bundle_aliases[i].path,&a);
    }
    bqt_sha_finish(&s,out);return 1;
}
static int bqt_bundle_ready(int root, const char *identity) {
    char expected[65],recorded[66]={0};
    if(!bqt_bundle_signature(root,identity,expected))return 0;
    int fd=openat(root,".ready",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return 0;
    ssize_t n=read(fd,recorded,sizeof recorded-1);close(fd);
    return n==65&&recorded[64]=='\n'&&!memcmp(recorded,expected,64);
}
static const char *bqt_bundle_mark_ready(int root, const char *identity) {
    char digest[66],temp[64];
    if(!bqt_bundle_signature(root,identity,digest))return "Bundled Qt files changed during extraction";
    digest[64]='\n';
    // Content reaches the disk before the stamp that vouches for it.
    if(syscall(SYS_syncfs,root))return bqt_bundle_fail("runtime sync",bqt_bundle_root);
    snprintf(temp,sizeof temp,".ready-%ld",(long)getpid());unlinkat(root,temp,0);
    int fd=openat(root,temp,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if(fd<0)return bqt_bundle_fail("runtime stamp",bqt_bundle_root);
    int failed=write(fd,digest,65)!=65;close(fd);
    if(failed||renameat(root,temp,root,".ready")){unlinkat(root,temp,0);return bqt_bundle_fail("runtime stamp",bqt_bundle_root);}
    return NULL;
}

// Each program holds a shared lock on its runtime directory's .use file for
// its lifetime and refreshes the file's time when it starts. At most once a
// day a starting program removes the other runtime directories that have not
// been used for a week and that no running program holds.
#define BQT_BUNDLE_UNUSED_SECONDS (7*24*3600)
#define BQT_BUNDLE_COLLECT_SECONDS (24*3600)
static int bqt_bundle_use=-1;
static void bqt_bundle_remove_tree(int parent, const char *name, int depth) {
    for(int pass=0;pass<2&&depth<64;pass++) {
        int fd=openat(parent,name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)break;
        DIR *entries=fdopendir(fd);if(!entries){close(fd);break;}
        struct dirent *entry;
        while((entry=readdir(entries))) {
            if(!strcmp(entry->d_name,".")||!strcmp(entry->d_name,".."))continue;
            if(unlinkat(dirfd(entries),entry->d_name,0)&&(errno==EISDIR||errno==EPERM))
                bqt_bundle_remove_tree(dirfd(entries),entry->d_name,depth+1);
        }
        closedir(entries);
        if(!unlinkat(parent,name,AT_REMOVEDIR)||errno!=ENOTEMPTY)break;
    }
}
static int bqt_bundle_hex_name(const char *name) {
    if(strlen(name)!=64)return 0;
    for(const char *p=name;*p;p++)if(!((*p>='0'&&*p<='9')||(*p>='a'&&*p<='f')))return 0;
    return 1;
}
static void bqt_bundle_collect(const char *base, const char *own) {
    int dir=open(base,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if(dir<0)return;
    int stamp=openat(dir,".collected",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
    struct stat st;time_t now=time(NULL);
    // An empty stamp has never recorded a collection.
    if(stamp<0||fstat(stamp,&st)||!S_ISREG(st.st_mode)||flock(stamp,LOCK_EX|LOCK_NB)
       ||(st.st_size>0&&now-st.st_mtime<BQT_BUNDLE_COLLECT_SECONDS)) {
        if(stamp>=0)close(stamp);close(dir);return;
    }
    if(st.st_size==0&&write(stamp,"\n",1)!=1){close(stamp);close(dir);return;}
    futimens(stamp,NULL);
    int listing=dup(dir);DIR *entries=listing<0?NULL:fdopendir(listing);
    if(!entries){if(listing>=0)close(listing);close(stamp);close(dir);return;}
    struct dirent *entry;
    while((entry=readdir(entries))) {
        const char *name=entry->d_name;
        if(!strncmp(name,".trash-",7)){bqt_bundle_remove_tree(dir,name,0);continue;}
        if(!bqt_bundle_hex_name(name)||!strcmp(name,own))continue;
        int child=openat(dir,name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if(child<0)continue;
        // Read the directory's time before .use might be created in it.
        struct stat cs,us;int use=-1;
        int keep=fstat(child,&cs)||cs.st_uid!=getuid()
                 ||(use=openat(child,".use",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600))<0
                 ||fstat(use,&us)||!S_ISREG(us.st_mode)
                 ||now-(us.st_size?us.st_mtime:cs.st_mtime)<BQT_BUNDLE_UNUSED_SECONDS
                 ||flock(use,LOCK_EX|LOCK_NB);
        if(!keep) {
            // Renaming first lets a program that is starting on this directory
            // notice and start over on a fresh one.
            char trash[NAME_MAX+1];snprintf(trash,sizeof trash,".trash-%.20s-%ld",name,(long)getpid());
            if(!renameat(dir,name,dir,trash)){close(use);use=-1;bqt_bundle_remove_tree(dir,trash,0);}
        }
        if(use>=0)close(use);close(child);
    }
    closedir(entries);close(stamp);close(dir);
}

// Writes every selected file that does not already match its content. Each
// decoded file is hashed as it is written and committed by rename.
static const char *bqt_bundle_extract(int root) {
    const char *error=NULL;void *zlib=dlopen("libz.so.1",RTLD_NOW|RTLD_LOCAL);
    int (*unpack)(unsigned char*,unsigned long*,const unsigned char*,unsigned long)=NULL;
    if(zlib){void *p=dlsym(zlib,"uncompress");memcpy(&unpack,&p,sizeof p);}
    if(!unpack){if(zlib)dlclose(zlib);return "Bundled Qt needs the system zlib runtime (libz.so.1)";}
    for(size_t i=0;i<@FILE_COUNT@&&!error;i++) {
        const BqtBundleFile *file=&bqt_bundle_files[i];char name[NAME_MAX+1];
        if(!bqt_bundle_selected(file))continue;
        int dir=bqt_bundle_parent(root,file->path,name);if(dir<0){error=bqt_bundle_fail("file directory",file->path);break;}
        int old=openat(dir,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
        int valid=old>=0&&bqt_bundle_matches(old,file);if(old>=0)close(old);
        if(valid){close(dir);continue;}
        char temp[64];snprintf(temp,sizeof temp,".bqt-%ld-%zu",(long)getpid(),i);
        // A previous crashed extraction may have left this process-id name.
        unlinkat(dir,temp,0);
        int fd=openat(dir,temp,O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
        if(fd<0){error=bqt_bundle_fail("temporary runtime file",file->path);close(dir);break;}
        BqtSha256 sha;bqt_sha_init(&sha);
        for(size_t j=0;j<file->count&&!error;j++) {
            const BqtBundleBlock *block=bqt_bundle_blocks[file->first+j];
            unsigned char *packed=malloc(block->packed?block->packed:1),*plain=malloc(block->plain?block->plain:1);
            if(!packed||!plain){free(packed);free(plain);error="Cannot allocate the bundled Qt decoder";break;}
            unsigned accumulator=0,bits=0;size_t bytes=0;int invalid=0;
            for(const unsigned char *p=(const unsigned char*)block->encoded;*p&&*p!='=';p++) {
                int digit=bqt_bundle_digit(*p);if(digit<0){invalid=1;break;}
                accumulator=accumulator<<6|(unsigned)digit;bits+=6;
                if(bits>=8){bits-=8;if(bytes>=block->packed){invalid=1;break;}packed[bytes++]=(unsigned char)(accumulator>>bits);}
            }
            unsigned long length=block->plain;
            if(invalid||bytes!=block->packed||unpack(plain,&length,packed,bytes)||length!=block->plain)error="Corrupt bundled Qt data";
            else {
                bqt_sha_update(&sha,plain,length);
                for(size_t offset=0;offset<length;) {
                    ssize_t wrote=write(fd,plain+offset,length-offset);
                    if(wrote<0&&errno==EINTR)continue;
                    if(wrote<=0){error=bqt_bundle_fail("runtime file write",file->path);break;}offset+=(size_t)wrote;
                }
            }
            free(packed);free(plain);
        }
        char digest[65];
        if(!error){bqt_sha_finish(&sha,digest);if(strcmp(digest,file->sha256))error="Bundled Qt file failed its content check";}
        if(!error&&fchmod(fd,file->mode))error=bqt_bundle_fail("runtime file mode",file->path);
        close(fd);
        if(!error&&renameat(dir,temp,dir,name))error=bqt_bundle_fail("runtime file commit",file->path);
        if(error)unlinkat(dir,temp,0);close(dir);
    }
    for(size_t i=0;i<@ALIAS_COUNT@&&!error;i++) {
        if(!bqt_bundle_selected(&bqt_bundle_files[bqt_bundle_aliases[i].target]))continue;
        char name[NAME_MAX+1],target_name[NAME_MAX+1];
        int dir=bqt_bundle_parent(root,bqt_bundle_aliases[i].path,name);
        const BqtBundleFile *file=&bqt_bundle_files[bqt_bundle_aliases[i].target];
        int target=bqt_bundle_parent(root,file->path,target_name);
        if(dir<0||target<0)error=bqt_bundle_fail("runtime alias directory",bqt_bundle_aliases[i].path);
        else {
            struct stat a,b;
            int same=!fstatat(dir,name,&a,AT_SYMLINK_NOFOLLOW)&&!fstatat(target,target_name,&b,AT_SYMLINK_NOFOLLOW)
                     &&S_ISREG(a.st_mode)&&a.st_dev==b.st_dev&&a.st_ino==b.st_ino;
            if(!same) {
                if(unlinkat(dir,name,0)&&errno!=ENOENT)error=bqt_bundle_fail("runtime alias removal",bqt_bundle_aliases[i].path);
                if(!error&&linkat(target,target_name,dir,name,0))error=bqt_bundle_fail("runtime alias",bqt_bundle_aliases[i].path);
            }
        }
        if(dir>=0)close(dir);if(target>=0)close(target);
    }
    dlclose(zlib);return error;
}

static int bqt_bundle_regular(int fd) {
    struct stat st;return fd>=0&&!fstat(fd,&st)&&S_ISREG(st.st_mode)&&st.st_uid==getuid();
}

static const char *bqt_bundle_materialize(void) {
    const char *override=getenv("BEND_QT_RUNTIME");
    if(override&&*override) {
        if(!realpath(override,bqt_bundle_root))return bqt_bundle_fail("explicit runtime override",override);
        return NULL;
    }
    if(bqt_bundle_invalid)return "Duplicate or invalid bundled Qt asset registration";
    for(size_t i=0;i<@FILE_COUNT@;i++) {
        const BqtBundleFile *file=&bqt_bundle_files[i];
        if(!bqt_bundle_selected(file))continue;
        for(size_t j=0;j<file->count;j++)
            if(!bqt_bundle_blocks[file->first+j])return "Missing bundled Qt asset import";
    }
    char identity[65]="@ID@";
#if @SELECTIVE@
    BqtSha256 digest;bqt_sha_init(&digest);
    bqt_sha_update(&digest,(const unsigned char*)identity,64);
    for(size_t i=0;i<@MODULE_COUNT@;i++)if(bqt_bundle_active[i/64]&(UINT64_C(1)<<(i%64)))
        bqt_sha_update(&digest,(const unsigned char*)bqt_bundle_module_names[i],strlen(bqt_bundle_module_names[i])+1);
    bqt_sha_finish(&digest,identity);
#endif
    const char *cache=getenv("XDG_CACHE_HOME"),*home=getenv("HOME");char base[PATH_MAX];
    if(cache&&*cache&&cache[0]=='/') {
        if(snprintf(base,sizeof base,"%s",cache)>=(int)sizeof base)return "Qt cache path is too long";
    } else {
        if(!home||home[0]!='/')return "Bundled Qt needs HOME or an absolute XDG_CACHE_HOME";
        if(snprintf(base,sizeof base,"%s/.cache",home)>=(int)sizeof base)return "Qt cache path is too long";
    }
    if(mkdir(base,0700)&&errno!=EEXIST)return bqt_bundle_fail("cache directory",base);
    size_t n=strlen(base);
    if(n+sizeof "/bend-qt" > sizeof base)return "Qt cache path is too long";
    strcpy(base+n,"/bend-qt");int parent=bqt_bundle_private_dir(base);
    if(parent<0)return bqt_bundle_fail("private cache",base);close(parent);
    if(snprintf(bqt_bundle_root,sizeof bqt_bundle_root,"%s/%s",base,identity)>=(int)sizeof bqt_bundle_root)return "Qt cache path is too long";
    int root=-1,use=-1;
    for(int attempt=0;attempt<8;attempt++) {
        root=bqt_bundle_private_dir(bqt_bundle_root);if(root<0)return bqt_bundle_fail("runtime directory",bqt_bundle_root);
        use=openat(root,".use",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
        if(!bqt_bundle_regular(use)||flock(use,LOCK_SH)) {
            if(use>=0)close(use);close(root);return bqt_bundle_fail("runtime use lock",bqt_bundle_root);
        }
        // Collection renames an unused directory before removing it. A program
        // that waited for it starts over on a fresh directory.
        struct stat held,named;
        if(!fstat(root,&held)&&!lstat(bqt_bundle_root,&named)&&held.st_dev==named.st_dev&&held.st_ino==named.st_ino)break;
        close(use);close(root);root=use=-1;
    }
    if(root<0)return "The bundled Qt runtime directory kept moving during startup";
    // The .use file's time records the last start; a non-empty file has one.
    struct stat used;
    if(!fstat(use,&used)&&used.st_size==0&&write(use,"\n",1)!=1){close(use);close(root);return bqt_bundle_fail("runtime use",bqt_bundle_root);}
    futimens(use,NULL);
    const char *error=NULL;
    if(!bqt_bundle_ready(root,identity)) {
        int lock=openat(root,".lock",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);
        if(!bqt_bundle_regular(lock)||flock(lock,LOCK_EX)) {
            if(lock>=0)close(lock);close(use);close(root);return bqt_bundle_fail("runtime lock",bqt_bundle_root);
        }
        // Another program may have completed the directory while this one waited.
        if(!bqt_bundle_ready(root,identity)) {
            unlinkat(root,".ready",0);
            error=bqt_bundle_extract(root);
            if(!error)error=bqt_bundle_mark_ready(root,identity);
        }
        flock(lock,LOCK_UN);close(lock);
    }
    close(root);
    if(error){close(use);return error;}
    // The shared lock lasts for the process lifetime: collection skips this directory.
    bqt_bundle_use=use;
    bqt_bundle_collect(base,identity);
    return NULL;
}
