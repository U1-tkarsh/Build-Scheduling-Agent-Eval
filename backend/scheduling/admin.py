from django.contrib import admin

from scheduling.models import (
    Appointment,
    AppointmentSlot,
    Conversation,
    Doctor,
    PromptVersion,
)

admin.site.register(Doctor)
admin.site.register(AppointmentSlot)
admin.site.register(Appointment)
admin.site.register(Conversation)
admin.site.register(PromptVersion)
