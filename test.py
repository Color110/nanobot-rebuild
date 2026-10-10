from pathlib import Path

from app.skills import SkillLoader
from app.skill_catalog import SkillCatalog
from app.skill_activation import SkillActivationResolver


loader = SkillLoader(Path("workspace"))

catalog = SkillCatalog(
    loader.list_skills()
)

resolver = SkillActivationResolver(catalog)


print("=== All Skills ===")
for skill in catalog.list_all():
    print(
        skill.name,
        skill.enabled,
        skill.always,
    )


print("\n=== Descriptors ===")
for descriptor in catalog.descriptors():
    print(
        descriptor.routing_text()
    )


result = resolver.resolve(
    "使用 $file-math 帮我处理"
)

print("\n=== Active Skills ===")

for activation in result.activations:
    print(
        activation.skill.name,
        activation.sources,
    )


print("\n=== Issues ===")

for issue in result.issues:
    print(
        issue.name,
        issue.reason,
    )
