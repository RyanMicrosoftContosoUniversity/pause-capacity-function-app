"""Fabric capacity lifecycle logic, kept out of ``function_app.py``.

``function_app.py`` is the *trigger* surface: schedules and bindings, nothing
else. Everything that decides what a pause or resume actually does lives here.

Import safety
-------------
Nothing in this package imports ``fabric_utils``, ``requests`` or
``azure.identity`` at module scope. Those imports happen inside the functions
that need them, so a broken dependency degrades to a failing *invocation*
rather than an app with zero registered triggers. See ``function_app`` for why
that distinction matters.
"""
