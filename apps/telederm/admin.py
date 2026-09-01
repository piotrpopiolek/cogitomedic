from django.contrib import admin

from apps.telederm.models import TeledermQuestionDefinition, TeledermQuestionOption


class TeledermQuestionOptionInline(admin.TabularInline):
    model = TeledermQuestionOption
    extra = 0


@admin.register(TeledermQuestionDefinition)
class TeledermQuestionDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "question_id",
        "path_code",
        "section",
        "answer_type",
        "is_required",
        "display_order",
        "is_active",
    )
    list_filter = ("path_code", "section", "is_active")
    search_fields = ("question_id", "question_text_de")
    inlines = [TeledermQuestionOptionInline]
