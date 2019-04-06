#!/usr/bin/env python
from ricecooker.chefs import SushiChef
from ricecooker.classes.nodes import ChannelNode, TopicNode, DocumentNode, HTML5AppNode
from ricecooker.classes.files import DocumentFile, HTMLZipFile
from ricecooker.classes.licenses import get_license


class HPLifeChef(SushiChef):
    channel_info = {
        'CHANNEL_TITLE': 'HP LIFE Sample Channel',
        'CHANNEL_SOURCE_DOMAIN': 'life-global.org',         # where you got the content (change me!!)
        'CHANNEL_SOURCE_ID': 'hp-life-sample-content',  # channel's unique id (change me!!)
        'CHANNEL_LANGUAGE': 'en',                        # le_utils language code
        'CHANNEL_THUMBNAIL': 'https://s10896.pcdn.co/wp-content/uploads/2015/08/HP-Life-Logo.jpg', # (optional)
        'CHANNEL_DESCRIPTION': 'This channel contains sample content exported from the Articulate Storyline format slideshows packaged as HTML5Zip',      # (optional)
    }

    def construct_channel(self, **kwargs):
        channel = self.get_channel(**kwargs)
        topic = TopicNode(title="Ariculate Storyline samples", source_id="sample_as")
        channel.add_child(topic)

        html_node1 = HTML5AppNode(
            title='Business Concept',
            description='The contents of Business Concept/ dir',
            source_id='business-concept',
            license=get_license('CC BY', copyright_holder='HP LIFE'),
            language='en',
            files=[HTMLZipFile(path='HP LIFE sample/Success Mindset - English/business-concept-webroot.zip',
                                language='en')],
        )
        topic.add_child(html_node1)

        # html_node2 = HTML5AppNode(
        #     title='Story',
        #     description='The contents of Story/ dir',
        #     source_id='story',
        #     license=get_license('CC BY', copyright_holder='HP LIFE'),
        #     language='en',
        #     files=[HTMLZipFile(path='HP LIFE sample/Success Mindset - English/story-webroot.zip',
        #                         language='en')],
        # )
        # topic.add_child(html_node2)

        return channel


if __name__ == '__main__':
    """
    Run this script on the command line using:
        python simple_chef.py -v --reset --token=YOURTOKENHERE9139139f3a23232
    """
    simple_chef = HPLifeChef()
    simple_chef.main()


