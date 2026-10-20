"""SDK availability checks are read-only and reject unavailable service state."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.probe_native_sdk import require_sdk_service,validate_staging
from logixlab.programming_lease import ProgrammingLease


class SdkAvailabilityTests(unittest.TestCase):
    def test_only_running_service_is_accepted_without_any_service_mutation(self):
        for state,code in (('Running\n',0),('Stopped\n',0),('StartPending\n',0),('',1),('Running\n',1)):
            with self.subTest(state=state,code=code),patch('tools.probe_native_sdk.subprocess.run',return_value=SimpleNamespace(returncode=code,stdout=state)) as command:
                if state=='Running\n' and code==0:require_sdk_service()
                else:
                    with self.assertRaises(ValueError):require_sdk_service()
                self.assertIn('Get-Service',command.call_args.args[0][-1])
                self.assertNotIn('Start-Service',command.call_args.args[0][-1])
                self.assertNotIn('Stop-Service',command.call_args.args[0][-1])

    def test_result_ledger_must_be_empty_with_private_data_and_vendor_encoding_disabled(self):
        lease=ProgrammingLease().description(1,'a'*64);validate_staging(lease)
        for field,value in (('status','available'),('records',1),('records',False),('operations',[{'count':1}]),
                ('immutable',False),('private_internal_only',False),('wire_encoding_supported',True),
                ('vendor_status_exposed',True),('request_bytes_exposed',True),('object_identifiers_exposed',True)):
            other=copy.deepcopy(lease)
            other['resilient_transport']['download_image']['preparation_results'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_staging(other)


if __name__=='__main__':unittest.main()
