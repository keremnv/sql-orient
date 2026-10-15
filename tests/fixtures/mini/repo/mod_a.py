"""Module A."""
CONSTANT = 41


def alpha(x):
    return helper(x) + CONSTANT


def helper(x):
    return x * 2


class K:
    def m(self):
        return 1


class J(K):
    def m(self):
        return 2


def outer():
    def inner():
        return 3
    return inner()


def deco(f):
    return f


@deco
def decorated():
    return 4
