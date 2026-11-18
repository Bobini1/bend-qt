// Matching Qt runtime assets, carried by ordinary foreign C imports.
// @TYPES@
// @CACHE@
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
static int bqt_bundle_digit(unsigned char c) {
    if(c>='A'&&c<='Z')return c-'A';if(c>='a'&&c<='z')return c-'a'+26;
    if(c>='0'&&c<='9')return c-'0'+52;if(c=='+')return 62;if(c=='/')return 63;return -1;
}

// A verified runtime directory's .ready stamp is a digest of every selected
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
static int bqt_bundle_signature(int root, const char *identity, char out[66]) {
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
    bqt_sha_finish(&s,out);out[64]='\n';out[65]=0;return 1;
}
// The shared lock on the runtime's .use file lasts for the process lifetime.
static int bqt_bundle_use=-1;

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
    char base[PATH_MAX],stamp[66];
    const char *error=bqt_cache_base(base);
    int root=-1,use=-1;
    if(!error)error=bqt_cache_hold(base,identity,bqt_bundle_root,&root,&use);
    if(error)return error;
    int ready=bqt_bundle_signature(root,identity,stamp)&&bqt_cache_ready(root,stamp);
    if(!ready) {
        int lock=bqt_cache_lock(root);
        if(lock<0){close(use);close(root);return bqt_bundle_fail("runtime lock",bqt_bundle_root);}
        // Another program may have completed the directory while this one waited.
        if(!bqt_bundle_signature(root,identity,stamp)||!bqt_cache_ready(root,stamp)) {
            unlinkat(root,".ready",0);
            error=bqt_bundle_extract(root);
            if(!error&&!bqt_bundle_signature(root,identity,stamp))error="Bundled Qt files changed during extraction";
            if(!error)error=bqt_cache_mark(root,stamp,bqt_bundle_root);
        }
        flock(lock,LOCK_UN);close(lock);
    }
    close(root);
    if(error){close(use);return error;}
    // The shared lock lasts for the process lifetime: collection skips this directory.
    bqt_bundle_use=use;
    bqt_cache_collect(base);
    return NULL;
}
