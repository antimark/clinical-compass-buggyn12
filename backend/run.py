import os
from cc_api import create_app
app=create_app()
if __name__=='__main__':
    app.run(host=os.getenv('CC_HOST','127.0.0.1'),port=int(os.getenv('CC_PORT','8000')),debug=False)
