from django.urls import path

from scheduling import views

urlpatterns = [
    path("chat/", views.chat, name="chat"),
    path("conversations/reset/", views.reset_conversation, name="reset_conversation"),
    path("conversations/<str:conversation_id>/", views.get_conversation, name="get_conversation"),
    path("evals/run/", views.run_evals_api, name="run_evals"),
    path("prompts/", views.prompt_versions, name="prompt_versions"),
]
