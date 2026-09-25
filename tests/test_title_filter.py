from app.manager import _title_has_keyword, _title_matches_job_filter


INCLUDE = ["vue", "nuxt", "fullstack", "full stack", "laravel", "php", "wordpress"]
EXCLUDE = ["react", "angular", "java", "c#", ".net"]


def test_missing_title_fails_closed():
    assert not _title_matches_job_filter("", INCLUDE, EXCLUDE)


def test_unrelated_jobs_are_rejected():
    for title in ("Электрик", "Повар", "Водитель-курьер", "Менеджер по продажам"):
        assert not _title_matches_job_filter(title, INCLUDE, EXCLUDE)


def test_target_stack_is_allowed():
    assert _title_matches_job_filter("Fullstack-разработчик (Laravel + Vue)", INCLUDE, EXCLUDE)
    assert _title_matches_job_filter("PHP-разработчик WordPress", INCLUDE, EXCLUDE)


def test_excluded_stack_wins_over_include():
    assert not _title_matches_job_filter("Fullstack Java Developer", INCLUDE, EXCLUDE)
    assert not _title_matches_job_filter("Vue + React разработчик", INCLUDE, EXCLUDE)


def test_java_does_not_match_javascript():
    assert not _title_has_keyword("JavaScript разработчик", "java")
    assert _title_has_keyword("Java разработчик", "java")
