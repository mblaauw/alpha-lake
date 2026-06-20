from alpha_lake.secrets import EnvSecretStore, StaticSecretStore, get_store, set_store


def test_env_secret_store_get_set_delete():
    store = EnvSecretStore(prefix="TEST_SECRETS_")
    store.set("my_key", "my_value")
    assert store.get("my_key") == "my_value"
    store.delete("my_key")
    assert store.get("my_key") == ""


def test_static_secret_store():
    store = StaticSecretStore()
    store.set("my_key", "my_value")
    assert store.get("my_key") == "my_value"
    assert store.get("nonexistent") == ""
    store.delete("my_key")
    assert store.get("my_key") == ""


def test_set_and_get_store():
    original = get_store()
    test_store = StaticSecretStore()
    set_store(test_store)
    assert get_store() is test_store
    set_store(original)
    assert get_store() is original
