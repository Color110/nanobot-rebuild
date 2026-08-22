from app.main import main


def test_main(capsys):
    main()

    output = capsys.readouterr().out

    assert "nanobot-rebuild" in output
    assert "status: OK" in output