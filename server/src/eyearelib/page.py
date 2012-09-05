from twisted.web import server, resource
from twisted.web.server import NOT_DONE_YET
import json, time
import eyearelib.logger as log
import eyearelib.permissions as perm
import eyearelib.database as database
from eyearelib.util import HashableDict

_LongRequest__openConnections = {}

def connections(user):
	try:
		return _LongRequest__openConnections[user]
	except KeyError:
		_LongRequest__openConnections[user] = []
		return _LongRequest__openConnections[user]

def connection(user,obj):
	return [obj == element for element in connections(user)][0]

def pollWaitingConnections(user):
	conns = connections(user)
	log.d("connections('%s') [%d]",user,len(conns))
	for conn in conns:
		request, args, output = conn.data
		log.d("%s -> %s",args['user'],output)
		conn.run(request, args, output)

def sanitize(request):
	args = {}
	for arg in request.args:
		args[str(arg)] = str(request.args[arg][0])
	return args

def exists(args, key):
	if key not in args.keys(): return False
	if args[key] in ['None', '']: return False
	return True

class Page(resource.Resource):
	isLeaf = False
	needsAuth = True
	needsAdmin = False
	needs = []

	def __init__(self):
		resource.Resource.__init__(self)

	def render_GET(self, request):
		args = sanitize(request)
		request.setHeader("content-type", "application/json")
		return self.validate(request, args)
		
	render_POST = render_GET	

	def validate(self, request, args):
		self.database = database.getInstance()
		output = {'status': 1, 'server_time': time.time()}
		dont_run = False
		status = 0
		if self.needsAuth is True:
			if not exists(args, 'user')\
			or not exists(args, 'token'):
				output['status'] = 2
				dont_run = True
			else:
				test = self.database.get('users',
				{'user': args['user']})[0]
				if test['token'] != args['token']:
					output['status'] = 3
					dont_run = True
				if self.needsAdmin is True\
				and (test['permissions'] & perm.ADMIN)\
				!= perm.ADMIN:
					output['status'] = 4
					dont_run = True
				for need in self.needs:
					if need not in args.keys()\
					or args[need] == '':
						output['status'] = 5
						dont_run = True
		try:
			if dont_run is False:
				status = self.run(request, args, output)
		except:
			log.trace()
			output['status'] = -1
		
		if status == server.NOT_DONE_YET:
			return server.NOT_DONE_YET
		return json.dumps(output, indent=2)		

	def run(self, request, args, output):
		output['payload'] = ["default Page does nothing"]

class LongRequest(Page):
	data = {}	

	def completed(self, request, args, output):
		self.process(request, args, output)
		request.write(json.dumps(output, indent=2))
		request.finish()
		request.notifyFinish()
		connections(args['user']).remove(self)

	def isReady(self, request, args, output):
		return True

	def process(self, request, args, output):
		pass

	def run(self, request, args, output):
		self.data = (request, args, output)
		if self.isReady(request, args, output):
			return self.completed(request, args, output)
		else:
			global __openConnections
			conns = __openConnections
			if args['user'] not in conns.keys():
				conns[args['user']] = [self]
			else:
				conns[args['user']].append(self)

			return server.NOT_DONE_YET

