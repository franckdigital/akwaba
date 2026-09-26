from django.db import migrations


def enable(apps, schema_editor):
    apps.get_model("pedagogy", "Course").objects.update(sequential=True)


class Migration(migrations.Migration):
    dependencies = [("pedagogy", "0008_alter_course_sequential")]
    operations = [migrations.RunPython(enable, migrations.RunPython.noop)]
