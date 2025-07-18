from cleanbox import create_app, init_db

app = create_app()

if __name__ == "__main__":
    # 개발 환경에서 DB 초기화
    init_db(app)
    app.run(debug=True)
