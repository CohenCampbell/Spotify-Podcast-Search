from flask import Flask, render_template, redirect, request, flash, session
from requests import post, get
from models import db, connect_db, User, Podcast, WatchList
from forms import RegisterForm, LoginForm, SpotifyPodcastSearchForm, SpotifyPodcastInfoForm, KeywordForm
from flask_bcrypt import Bcrypt
import os, base64, json


app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("SQLALCHEMY_DATABASE_URI_TEST")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = False

connect_db(app)
bcrypt = Bcrypt()

client_id = os.environ.get("CLIENT_ID")
client_secret = os.environ.get("CLIENT_SECRET")
redirect_uri = "http://127.0.0.1:5000/"


def get_spotify_token(code):
    
    auth_string = client_id + ":" + client_secret
    auth_string64 = base64.b64encode(auth_string.encode()).decode()
    url = "https://accounts.spotify.com/api/token"

    headers = {
        'Authorization': "Basic " + auth_string64,
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {'grant_type': 'client_credentials',
            'code': code,
            'redirect_uri': redirect_uri}
    
    result = post(url, headers=headers, data=data)
    
    token = json.loads(result.content)
    print(token["access_token"])
    return token["access_token"]



@app.route("/create_db")
def db_creation():

    db.create_all()
    return redirect("/")

@app.route("/")
def homepage():

    if "user_id" not in session:
        flash("You must be logged in to view that page!")
        return redirect("/login")

    #check if the user accepts the request, if not flashes an error
    if "error" in request.args:
        flash("You must accept the request or the application cannot function")
        return redirect("/login")

    # getting spotify code, needed for spotify token, assigned None if it's not in query str
    if request.args:
        code = request.args["code"]
        session["code"] = code
    else:
    # Gets code if it wasn't in query str
        return redirect(f"https://accounts.spotify.com/en/authorize?response_type=code&redirect_uri={redirect_uri}&client_id={client_id}")
    
    user = User.get_by_id(session["user_id"])
    if(user == None):
        return redirect("/register")

    return render_template("/homepage.html", admin=user.admin)

@app.route("/register", methods=["GET"])
def get_register():

    form = RegisterForm()
    return render_template("register.html", form=form)

@app.route("/register", methods=["POST"])
def post_register():

    form = RegisterForm()
    if(form.validate_on_submit()):
        username = form.username.data
        password = form.password.data
        email = form.email.data
        
        new_user = User.register(username, password, email)
        db.session.commit()
        
        session["user_id"] = new_user.id
        session["admin"] = new_user.admin
        return redirect("/")
    flash("There was an error!")
    return redirect("/register")

@app.route("/login", methods=["GET"])
def get_login():

    form = LoginForm()
    return render_template("login.html", form=form)

@app.route("/login", methods=["POST"])
def post_login():

    form = LoginForm()
    username = form.username.data
    password = form.password.data

    logged_user = User.get_by_username(username)
    if(logged_user == None):
        flash("Incorrect username or password")
        return redirect("/login")
    
    session["user_id"] = logged_user.id
    session["admin"] = logged_user.admin
    return redirect("/")
    

@app.route("/logout", methods=["GET"])
def logout():

    session.clear()
    flash("You have logged out!")
    return redirect("/login")

@app.route("/podcastAPI", methods=["POST"])
def podcast_post():

    form = SpotifyPodcastSearchForm()

    if(form.validate_on_submit()):
        query = form.search.data.replace(" ", "+")
        code = session["code"]
    else:
        flash("There was an error with your search. Please try again!")
        return redirect("/podcastAPI")

    url = f"https://api.spotify.com/v1/shows/{query}"
    token = get_spotify_token(code)
    headers = {'Authorization': 'Bearer ' + token}
    
    results = get(url, headers=headers)
    results_json = json.loads(results.content)
    
    
    if results.json:
        if "error" in results_json:
            flash("invalid id")
            return redirect("/podcastAPI")

        show = dict(name = results_json["name"], 
                description = results_json["description"], 
                host = results_json["publisher"], 
                image_url = results_json["images"][0]["url"],
                podcast_id = results_json["id"])
        
        return render_template("/podcastAPI.html", form=form, podcast=show, data_form=SpotifyPodcastInfoForm())

    return redirect("/podcast")

@app.route("/podcastAPI", methods=["Get"])
def podcast_get():
    
    if "user_id" not in session:
        flash("You must be logged in to view that page!")
        return redirect("/login")
    elif session["admin"] != True:
        flash("You must be an admin to view that page!")
        return redirect("/")

    form = SpotifyPodcastSearchForm()
    
    return render_template("/podcastAPI.html", form=form)

@app.route("/podcast", methods=["GET"])
def show_podcast_db():

    if "user_id" not in session:
        flash("You must be logged in to view that page!")
        return redirect("/login")
    user = User.get_by_id(session["user_id"])
    podcasts = Podcast.query.all();

    return render_template("/podcast.html", podcasts=podcasts, admin=user.admin, user=user)

@app.route("/podcast", methods=["POST"])
def podcast_add_db():
    
    form = SpotifyPodcastInfoForm()
    if(form.validate_on_submit()):
        new_podcast = Podcast.add_podcast(host=form.host.data, title=form.title.data, 
                                          description=form.description.data, img_url=form.img_url.data, 
                                          podcast_id_spotify=form.podcast_id_spotify.data)
        db.session.commit()
        flash(f"{form.title.data} was added to the database!")
        return redirect("/podcastAPI")
    return redirect("/podcastAPI")

@app.route("/podcast/<int:id>", methods=["GET"])
def podcastID_get(id):

    if "user_id" not in session:
        flash("You must be logged in to view that page!")
        return redirect("/login")
    
    form = KeywordForm()
    podcast = Podcast.get_by_id(id)
    watchlist = WatchList.get_watchlist(user_id=session["user_id"])
    watchlist_ids = [];
    for item in watchlist:
        watchlist_ids.append(item.podcast_id)

    return render_template("/podcastID.html", podcast=podcast, watchlist_ids=watchlist_ids, form=form)
    
@app.route("/podcast/remove/<int:id>", methods=["POST"])
def podcastID_post(id):

    if session["admin"] != True:
        flash("You must be an admin to view that page!")
        return redirect("/")
    
    Podcast.delete_podcast(id)
    db.session.commit()

    return redirect("/podcast")

@app.route("/watchlist/<int:podcast_id>", methods=["POST"])
def watchlist_post(podcast_id):

    if "user_id" not in session:
        flash("You must be logged in to view that page!")
        return redirect("/login")

    new_item = WatchList.add_item(user_id=session["user_id"], podcast_id=podcast_id)
    db.session.commit()

    return redirect(f"/podcast/{podcast_id}")

@app.route("/watchlist/<int:id>", methods=["GET"])
def watchlist_get(id):
    
    if "user_id" not in session:
        flash("You must be logged in to view that page!")
        return redirect("/login")
    elif session["user_id"] != id:
        return redirect(f"/watchlist/{session['user_id']}")
        
    user = User.get_by_id(id)
    watchlist = WatchList.get_watchlist(id)
    podcasts = []
    for item in watchlist:
        podcasts.append(Podcast.get_by_id(item.podcast_id))
    return render_template("/watchlist.html", watchlist=watchlist, user=user, podcasts=podcasts)

@app.route("/watchlist/remove/<int:podcast_id>", methods=["POST"])
def watchlist_delete(podcast_id):

    if "user_id" not in session:
        flash("You must be logged in to view that page!")
        return redirect("/login")
    
    WatchList.remove_item(session["user_id"], podcast_id)
    db.session.commit()

    return redirect("/podcast")

@app.route("/search/<int:podcast_id>", methods=["POST"])
def search_episode(podcast_id):
    form = KeywordForm()
    keyword = form.keyword.data
    podcast = Podcast.get_by_id(podcast_id)
    user = User.get_by_id(session["user_id"])
    offset = form.offset.data or 0
    episodes= []
    watchlist = WatchList.get_watchlist(user_id=session["user_id"])
    watchlist_ids = [];
    
    for item in watchlist:
        watchlist_ids.append(item.podcast_id)

    url = f"https://api.spotify.com/v1/shows/{podcast.podcast_id_spotify}/episodes?limit=50&offset={offset}"                           #f'https://api.spotify.com/v1/search?q={query}&type=show&limit=5'
    token = get_spotify_token(session["code"])
    headers = {'Authorization': 'Bearer ' + token}
    
    results = get(url, headers=headers)
    results_json = json.loads(results.content)
    if "items" not in results_json:
            flash("The offset was too high")
            return redirect(f"/podcast/{podcast_id}")
    for episode in results_json["items"]:
        if keyword in episode["description"]:
            episodes.append(episode["name"])
    if(len(episodes) == 0):
        flash(f"No episodes were found using the word {keyword}!")
        
    return render_template("/podcastID.html", podcast=podcast, form=form,
                               watchlist_ids=watchlist_ids, episodes=episodes)
     
