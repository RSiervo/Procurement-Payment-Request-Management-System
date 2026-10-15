from django.db import transaction
from rest_framework import serializers

from apps.requests.models import RequestType

from .models import ApproverType, Workflow, WorkflowStep


class WorkflowStepSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True, default="")
    user_name = serializers.CharField(source="user.display_name", read_only=True, default="")
    level_name = serializers.CharField(source="level.name", read_only=True, default="")

    class Meta:
        model = WorkflowStep
        fields = ["id", "order", "name", "level", "level_name", "approver_type",
                  "role", "role_name", "user", "user_name", "after_ops"]
        read_only_fields = ["order"]

    def validate(self, attrs):
        kind = attrs["approver_type"]
        if kind == ApproverType.ROLE and not attrs.get("role"):
            raise serializers.ValidationError({"role": "Choose the role that approves this step."})
        if kind == ApproverType.USER and not attrs.get("user"):
            raise serializers.ValidationError({"user": "Choose the user who approves this step."})
        attrs["role"] = attrs.get("role") if kind == ApproverType.ROLE else None
        attrs["user"] = attrs.get("user") if kind == ApproverType.USER else None
        return attrs


class WorkflowSerializer(serializers.ModelSerializer):
    steps = WorkflowStepSerializer(many=True)
    request_type = serializers.SlugRelatedField(slug_field="code", queryset=RequestType.objects.all())
    request_type_name = serializers.CharField(source="request_type.name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default="")

    class Meta:
        model = Workflow
        fields = ["id", "name", "description", "request_type", "request_type_name", "department",
                  "department_name", "min_amount", "max_amount", "priority", "requires_ops_processing",
                  "is_active", "steps", "updated_at"]

    def validate_steps(self, steps):
        if not steps:
            raise serializers.ValidationError("A workflow needs at least one approval step.")
        seen_after = False
        for step in steps:
            if seen_after and not step.get("after_ops"):
                raise serializers.ValidationError(
                    "Steps that approve before OPS processing must come before the steps that approve after it."
                )
            seen_after = seen_after or bool(step.get("after_ops"))
        return steps

    def validate(self, attrs):
        low = attrs.get("min_amount", getattr(self.instance, "min_amount", None))
        high = attrs.get("max_amount", getattr(self.instance, "max_amount", None))
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError({"max_amount": "The upper amount must not be below the lower amount."})
        steps = attrs.get("steps")
        with_ops = attrs.get("requires_ops_processing", getattr(self.instance, "requires_ops_processing", True))
        if steps and not with_ops and any(step.get("after_ops") for step in steps):
            raise serializers.ValidationError(
                {"steps": "Steps after OPS processing need \"Send to OPS for processing\" switched on."}
            )
        return attrs

    def _write_steps(self, workflow, steps):
        workflow.steps.all().delete()
        WorkflowStep.objects.bulk_create(
            WorkflowStep(workflow=workflow, order=order, **step) for order, step in enumerate(steps, start=1)
        )

    @transaction.atomic
    def create(self, validated):
        steps = validated.pop("steps")
        workflow = Workflow.objects.create(**validated)
        self._write_steps(workflow, steps)
        return workflow

    @transaction.atomic
    def update(self, workflow, validated):
        steps = validated.pop("steps", None)
        for field, value in validated.items():
            setattr(workflow, field, value)
        workflow.save()
        if steps is not None:
            self._write_steps(workflow, steps)
        return workflow
