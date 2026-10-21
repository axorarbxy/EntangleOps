from __future__ import annotations
from security.tickets import TicketService

def test_ticket_is_bound_and_single_use():
    tickets=TicketService("t"*40,30);ticket=tickets.issue("key-id","run-id")
    assert tickets.redeem(ticket,"run-id")=="key-id"
    assert tickets.redeem(ticket,"run-id") is None
    assert tickets.redeem(tickets.issue("key-id","run-id"),"other-run") is None
