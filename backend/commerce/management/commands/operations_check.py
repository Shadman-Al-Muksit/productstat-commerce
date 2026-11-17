import json
from django.core.management.base import BaseCommand
from django.db import DatabaseError
from django.utils import timezone
from commerce.monitoring import operations_health

class Command(BaseCommand):
    help='Print redacted operational health JSON. Exit0=clear,1=attention,2=database unavailable. Sends no notifications.'
    def handle(self,*args,**options):
        try:
            report=operations_health()
        except DatabaseError:
            self.stdout.write(json.dumps({'status':'unavailable','checked_at':timezone.now().isoformat(),'detail':'Operational database checks could not be completed.'}))
            raise SystemExit(2)
        self.stdout.write(json.dumps(report))
        if report['status']=='attention': raise SystemExit(1)
