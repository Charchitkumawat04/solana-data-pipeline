from firstclass import llms

class chatbot(llms):

    def __init__(self, model, query):
        self.model = model
        llms.__init__(self, query)

    def showme(self):
        print("I am calling {self.model}.")
        llms.openai()

obj_inherit = chatbot("claude", "hi1")
print(obj_inherit.claude())