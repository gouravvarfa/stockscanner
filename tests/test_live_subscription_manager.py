from backend.live.subscription_manager import SubscriptionManager


def _manager():
    events = []

    async def on_first(symbol):
        events.append(("subscribe", symbol))

    async def on_last(symbol):
        events.append(("unsubscribe", symbol))

    return SubscriptionManager(on_first, on_last), events


async def test_first_acquire_triggers_subscribe():
    manager, events = _manager()
    await manager.acquire("BHEL")
    assert events == [("subscribe", "BHEL")]
    assert manager.is_subscribed("BHEL")
    assert manager.refcount("BHEL") == 1


async def test_second_acquire_for_the_same_symbol_does_not_resubscribe():
    manager, events = _manager()
    await manager.acquire("BHEL")
    await manager.acquire("BHEL")
    assert events == [("subscribe", "BHEL")]  # only once
    assert manager.refcount("BHEL") == 2


async def test_release_before_the_last_reference_does_not_unsubscribe():
    manager, events = _manager()
    await manager.acquire("BHEL")
    await manager.acquire("BHEL")
    await manager.release("BHEL")
    assert events == [("subscribe", "BHEL")]  # no unsubscribe yet
    assert manager.is_subscribed("BHEL")
    assert manager.refcount("BHEL") == 1


async def test_releasing_the_last_reference_unsubscribes():
    manager, events = _manager()
    await manager.acquire("BHEL")
    await manager.acquire("BHEL")
    await manager.release("BHEL")
    await manager.release("BHEL")
    assert events == [("subscribe", "BHEL"), ("unsubscribe", "BHEL")]
    assert not manager.is_subscribed("BHEL")


async def test_release_of_an_unsubscribed_symbol_is_a_harmless_noop():
    manager, events = _manager()
    await manager.release("NEVER_SUBSCRIBED")
    assert events == []


async def test_symbols_are_tracked_independently():
    manager, events = _manager()
    await manager.acquire("BHEL")
    await manager.acquire("RELIANCE")
    await manager.release("BHEL")
    assert not manager.is_subscribed("BHEL")
    assert manager.is_subscribed("RELIANCE")
    assert set(events) == {("subscribe", "BHEL"), ("subscribe", "RELIANCE"), ("unsubscribe", "BHEL")}


async def test_resubscribing_after_a_full_release_triggers_subscribe_again():
    manager, events = _manager()
    await manager.acquire("BHEL")
    await manager.release("BHEL")
    await manager.acquire("BHEL")
    assert events == [("subscribe", "BHEL"), ("unsubscribe", "BHEL"), ("subscribe", "BHEL")]


def test_subscribed_symbols_lists_only_active_ones():
    manager, _ = _manager()
    assert manager.subscribed_symbols() == []
