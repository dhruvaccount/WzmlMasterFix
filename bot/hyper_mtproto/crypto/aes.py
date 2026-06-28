import tgcrypto


def ctr256_encrypt(data, key, iv, state=None):
    return tgcrypto.ctr256_encrypt(data, key, iv, state)


def ctr256_decrypt(data, key, iv, state=None):
    return tgcrypto.ctr256_decrypt(data, key, iv, state)


def ige_encrypt(data, key, iv):
    return tgcrypto.ige_encrypt(data, key, iv)


def ige_decrypt(data, key, iv):
    return tgcrypto.ige_decrypt(data, key, iv)
