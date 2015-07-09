import json
import psutil

from uploader import get_info

from file_tools import file_manager


class session_state(object):
    """description of class"""
    """
    meta data about for a session
    """
    server_path = ''

    user = ''
    user_full_name = ''
    password = ''

    current_user = None
    current_time = ''
    instrument = ''
    instrument_friendly = ''
    proposal_friendly = ''
    proposal_id = ''
    proposal_user = ''

    files = file_manager()

    # meta data values
    meta_list = []

    # proposals
    proposal_list = []
    proposal_users = []

    # process that handles bundling and uploading
    bundle_process = None

    bundle_filepath = ''
    free_size_str = ''

    # free disk space
    free_space = 0

    # configuration dictionary
    configuration = {}

    def load_proposal (self, proposal):
        self.proposal_friendly = proposal

        # split the proposal string into ID and description
        split = self.proposal_friendly.split()
        self.proposal_id = split[0]

    def load_request_proposal (self, request):
        # get the selected proposal string from the post
        proposal = request.POST.get('proposal')
        self.load_proposal(proposal)

    def load_request_proposal_user (self, request):
        # get the selected proposal string from the post
        self.proposal_user = request.POST.get('proposal_user')

    def concatenated_instrument(self):
        """
        concatenate the instrument id with the description
        """
        return self.instrument + " " + self.instrument_friendly

    def clear_upload_lists(self):
        """
        clears the directory and file lists
        """
        self.selected_files = []
        self.selected_dirs = []

    def populate_user_info(self):
        """
        parses user information from a json struct
        """
        # get the user's info from EUS
        info = get_info(protocol='https',
            server=self.server_path,
            user=self.user,
            password=self.password,
            info_type = 'userinfo')

        #with open ('aslipton.json', 'r') as myfile:
        #    info=myfile.read()
        try:
            info = json.loads(info)
        except Exception:
            return 'Unable to parse user information'

        # print json.dumps(info, sort_keys=True, indent=4, separators=(',', ': '))

        first_name = info['first_name']
        if not first_name:
            return 'Unable to parse user name'
        last_name = info['last_name']
        if not last_name:
            return 'Unable to parse user name'

        self.user_full_name = '%s (%s %s)' % (self.user, first_name, last_name)

        instruments = info['instruments']
        if not instruments:
            return 'User is not valid for this instrument'

        try:
            valid_instrument = False
            for inst_id, inst_block in instruments.iteritems():
                if not inst_id:
                    continue
                if not inst_block:
                    continue
                inst_name = inst_block.get('instrument_name')
                if not inst_name:
                    inst_name = 'unnamed'
                inst_str = inst_id + ' ' + inst_name
                if self.instrument == inst_id:
                    self.instrument_friendly = inst_name
                    valid_instrument = True
                    break

            if not valid_instrument:
                return 'User is not valid for this instrument'
        except Exception:
            return 'Unable to parse user instruments'

        """
        need to filter proposals based on the existing instrument 
        if there is no valid proposal for the user for this instrument
        throw an error
        """
        props = info["proposals"]
        if not props:
            return 'user has no proposals'

        self.proposal_list = []
        for prop_id, prop_block in props.iteritems():

            if not prop_id:
                continue

            if not prop_block:
                continue

            title = prop_block.get('title')
            # if the title is missing we've established that it isn't in the db
            # so skip it
            if not title:
                continue;

            prop_str = prop_id + "  " + title

            # list only proposals valid for this instrument
            instruments = prop_block.get('instruments')
            if not instruments:
                continue

            try:
                for inst_id in instruments:
                    if not inst_id:
                        continue;
                    if self.instrument == str(inst_id):
                        if prop_str not in self.proposal_list:
                            self.proposal_list.append(prop_str)
            except Exception, err:
                return 'No valid proposals for this user on this instrument 166'

        if not self.proposal_list:
            return 'No valid proposals for this user on this instrument 169'

        #self.proposal_list.sort(key=lambda x: int(x.split(' ')[0]), reverse=True)
        self.proposal_list.sort(reverse=True)

        # initialize the proposal to the first in the list
        self.load_proposal(self.proposal_list[0])

        # initialize the user list
        self.populate_proposal_users()

        # no errors found
        return ''


    def populate_proposal_users(self):
        """
        parses user for a proposal and instrument from a json struct
        """

        # get the user's info from EUS
        info = get_info(protocol='https',
                         server=self.server_path,
                         user=self.user,
                         password=self.password,
                         info_type = 'proposalinfo/' + self.proposal_id)

        try:
            info = json.loads(info)
        except Exception:
            return 'Unable to parse proposal user information'

        # print json.dumps(info, sort_keys=True, indent=4, separators=(',', ': '))

        self.proposal_users = []

        members = info['members']
        # is this an error?  
        if not members:
            self.proposal_users.append('No users for this proposal')
            return

        for member in members.iteritems():
            id =  member[1]
            first_name = id['first_name']
            if not first_name:
                first_name = "?"
            last_name = id['last_name']
            if not last_name:
                last_name = '?'
            self.proposal_users.append(first_name + " " + last_name)

        #initialize the selected user
        if self.proposal_users:
            self.proposal_user = self.proposal_users[0]

    def cleanup_session(self):
        """
        resets a session to a clean state
        """
        self.instrument = None
        self.proposal_id = None
        self.proposal_list = []
        self.proposal_users = []
        self.user = ''
        self.password = ''
        self.user_full_name = ''
        self.cleanup_upload()

    def cleanup_upload(self):
        """
        resets a session to a clean state
        """
        self.bundle_process = None
        self.current_time = None
        self.files.cleanup_files()

    def validate_space_available(self, target_path):
        """
        check the bundle size agains space available
        """
        if target_path is None:
            return False

        self.files.calculate_bundle_size()

        # get the disk usage
        space = psutil.disk_usage(target_path)

        #give ourselves a cushion for other processes
        self.free_space = int(.9 * space.free)

        self.free_size_str = self.files.size_string(self.free_space)

        if (self.files.bundle_size == 0):
            return True
        return (self.files.bundle_size <  self.free_space)

    def write_default_config (self, filename):
        d = {}
        d['target'] = '/srv/localdata'
        d['dataRoot '] = '/srv/home'
        d['timeout'] = '10'
        d['server'] = 'dev1.my.emsl.pnl.gov'
        d['instrument'] = '0a'

        with open (filename, 'w') as fp:
            json.dump(d, fp)

    def read_config (self, filename):

        with open (filename, 'r') as fp:
            self.configuration = json.load(fp)