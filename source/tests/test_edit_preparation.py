"""Captured native edit reservation is exclusive and does not mutate logic."""
import copy
import unittest

import test_programming_lease as leases
import test_run_inhibit as inhibits
import test_programming_preparation as preparation

EDIT=bytes.fromhex('4b04208e24012074240101')


class EditReservationSignedTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare
    second_client=leases.SemaphoreSignedTests.second_client

    def test_captured_accept_edits_reserves_and_releases_without_changing_model(self):
        self.prepare();before=copy.deepcopy(self.app.state())
        self.assertEqual(self.signed(4,EDIT),bytes.fromhex('cb000000'))
        self.assertEqual(self.signed(5,EDIT),bytes.fromhex('cb000000'))
        state=self.endpoint.state()['native_programming_lease']
        self.assertEqual(state['request_selector'],1)
        self.assertEqual(state['edit_preparation']['status'],'reserved')
        self.assertEqual(state['edit_preparation']['changes_staged'],0)
        for field in ('online_edits','project_transfer','tag_write_authority','scan_inhibited'):
            self.assertFalse(state[field])
        self.assertEqual(self.signed(6,leases.ACQUIRE)[2],12)
        self.assertEqual(self.signed(7,leases.RELEASE)[2],0)
        after=self.app.state()
        for key in ('tags','routines','tasks','entry_routines','scan','ms','controller'):
            self.assertEqual(before[key],after[key],key)
        state=self.endpoint.state()['native_programming_lease']
        self.assertIsNone(state['request_selector'])
        self.assertEqual(state['edit_preparation']['status'],'idle')

    def test_edit_reservation_cannot_start_download_or_inhibit_scans(self):
        self.prepare();self.assertEqual(self.signed(4,EDIT)[2],0)
        self.assertEqual(self.signed(5,inhibits.SET)[2],15)
        self.assertEqual(self.signed(6,preparation.BEGIN)[2],15)
        state=self.endpoint.state()['native_programming_lease']
        self.assertEqual(state['run_mode_inhibit'],0)
        self.assertEqual(state['preparation_state'],'idle')
        self.assertEqual(state['edit_preparation']['status'],'reserved')
        self.assertEqual(self.signed(7,leases.RELEASE)[2],0)

    def test_unbound_context_and_foreign_owner_cannot_obtain_edit_reservation(self):
        self.begin();self.assertEqual(self.signed(1,EDIT)[2],15)
        self.prepare();self.assertEqual(self.signed(4,EDIT)[2],0)
        first=self.client;second=self.second_client()
        try:
            self.client=second
            self.assertEqual(self.signed(4,EDIT)[2],12)
            self.assertEqual(self.signed(5,leases.RELEASE)[2],15)
        finally:self.client=first;second.close()
        self.assertEqual(self.signed(5,leases.RELEASE)[2],0)


if __name__=='__main__':unittest.main()
