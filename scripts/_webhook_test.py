"""Throwaway file to trigger a real end-to-end webhook review. Safe to close/delete
this PR without merging once the review comment shows up."""


def add_item(item, bag=[]):
    bag.append(item)
    return bag


def load_config(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        pass
