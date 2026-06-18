from services.portrait_quality import PortraitQualityError

class TemplateError(Exception):
    def __init__(self, code, message, template_id="", status_code=400):
        self.code = code
        self.message = message
        self.template_id = template_id
        self.status_code = status_code
        super().__init__(self.message)
