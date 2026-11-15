using ConverterCleanupState = QStringConverterBase::State;
// The Bend handler Qt runs when it clears this state. Qt may clear a state on
// any thread; the handler itself runs on the main thread.
struct ConverterCleanupHolder {
    uint32_t handler;
    ~ConverterCleanupHolder() { callback_release_handler(handler); }
};
struct ConverterCleanupSnapshot {
    QStringConverterBase::Flags flags;
    int internal;
    qsizetype remaining, invalid;
};
static void converter_cleanup_native(ConverterCleanupState *) noexcept;
static unsigned converter_cleanup_admission(ConverterCleanupState *state, bool active) {
    uint32_t data[4]; std::memcpy(data, state->state_data, sizeof(data));
    bool empty = !state->clearFn && !(data[0] | data[1] | data[2] | data[3]);
    bool ours = state->clearFn == converter_cleanup_native;
    bool icu = state->flags.testFlag(QStringConverterBase::Flag::UsesIcu);
    return lifetime_cleanup_install[unsigned(empty)*8 + unsigned(ours)*4 + unsigned(icu)*2 + unsigned(active)];
}
static bool converter_cleanup_access(BqtRequest *r, ConverterCleanupState *state, bool allowed) {
    auto *e=entry(r->self);
    if (e && (e->active_calls > 1)) { fail(r, EBUSY, "Converter state is in an active native call"); return false; }
    if (state->clearFn != converter_cleanup_native) return true;
    if (!allowed) { fail(r, ENOTSUP, "Native method has no reserved cleanup-storage contract"); return false; }
    if (state->flags.testFlag(QStringConverterBase::Flag::UsesIcu)) { fail(r, EINVAL, "A Bend cleanup holder is not ICU codec storage"); return false; }
    return true;
}
static bool converter_cleanup_argument(BqtRequest *r, uint32_t id) {
    auto *state=get<ConverterCleanupState>(r,id,@STATE@,false,false);
    if (!state) return false;
    if (state->clearFn == converter_cleanup_native) { fail(r, ENOTSUP, "Native argument has no reserved cleanup-storage contract"); return false; }
    return true;
}
// The handler gets a copy of the fields: Qt has already cleared the state.
static void converter_cleanup_invoke(uint32_t handler, const ConverterCleanupSnapshot &snapshot) {
    CallbackOwnedArguments arguments{sequence_value(4)};
    arguments.value.items[0].word=uint32_t(snapshot.flags.toInt());
    arguments.value.items[1].word=uint32_t(snapshot.internal);
    arguments.value.items[2].word=uint32_t(uint64_t(snapshot.remaining));
    arguments.value.items[2].high=uint32_t(uint64_t(snapshot.remaining)>>32);
    arguments.value.items[3].word=uint32_t(uint64_t(snapshot.invalid));
    arguments.value.items[3].high=uint32_t(uint64_t(snapshot.invalid)>>32);
    if (int error=callback_invoke(handler,0,arguments.take(),callback_decode_unit,nullptr))
        callback_report_error(error);
}
static void converter_cleanup_native(ConverterCleanupState *state) noexcept {
    // Move construction/assignment transfers this public union and clearFn,
    // then clears the source clearFn. Detach before entering any user code.
    std::unique_ptr<ConverterCleanupHolder> holder(static_cast<ConverterCleanupHolder *>(state->d[0]));
    ConverterCleanupSnapshot snapshot{state->flags,state->internalState,state->remainingChars,state->invalidChars};
    state->clearFn=nullptr;
    std::memset(state->state_data,0,sizeof(state->state_data));
    if (!holder) return;
    auto invoke=[&] {
        try { converter_cleanup_invoke(holder->handler,snapshot); }
        catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }
        catch (...) { callback_report_error(EFAULT); }
    };
    try {
        if (QThread::currentThread()==main_thread) { invoke(); return; }
        // The snapshot is a copy, so the handler needs nothing from the state.
        callback_on_main(std::make_shared<std::atomic<bool>>(true), invoke);
    } catch (...) {
        // Qt's cleanup function is noexcept: the state is cleared regardless.
    }
}
static bool converter_cleanup_install(BqtRequest *r) {
    NativeCallScope scope;
    auto *state=get<ConverterCleanupState>(r,r->self,@STATE@,false,true);
    if (r->error) return true;
    auto error=converter_cleanup_admission(state,retained(r->self) || entry(r->self)->active_calls>1);
    if (error) return fail(r,error,"A cleanup handler requires idle unborrowed state with empty or Bend-owned storage and no ICU flag");
    auto next=std::make_unique<ConverterCleanupHolder>();
    next->handler=r->arguments[0].word;
    std::unique_ptr<ConverterCleanupHolder> old;
    if (state->clearFn==converter_cleanup_native) old.reset(static_cast<ConverterCleanupHolder *>(state->d[0]));
    std::memset(state->state_data,0,sizeof(state->state_data));
    state->d[0]=next.release(); state->clearFn=converter_cleanup_native;
    return true;
}
static bool converter_cleanup_remove(BqtRequest *r) {
    NativeCallScope scope;
    auto *state=get<ConverterCleanupState>(r,r->self,@STATE@,false,true);
    if (r->error) return true;
    auto error=converter_cleanup_admission(state,retained(r->self) || entry(r->self)->active_calls>1);
    if (error) return fail(r,error,"Opaque native cleanup/storage cannot be removed");
    std::unique_ptr<ConverterCleanupHolder> old;
    if (state->clearFn==converter_cleanup_native) old.reset(static_cast<ConverterCleanupHolder *>(state->d[0]));
    state->clearFn=nullptr; std::memset(state->state_data,0,sizeof(state->state_data));
    return true;
}
static bool converter_cleanup_installed(BqtRequest *r) {
    NativeCallScope scope;
    auto *state=get<ConverterCleanupState>(r,r->self,@STATE@,false,false);
    if (r->error) return true;
    if (state->clearFn && state->clearFn!=converter_cleanup_native) return fail(r,ENOTSUP,"Native cleanup function is not a Bend handler");
    r->result.word=state->clearFn != nullptr;
    return true;
}
